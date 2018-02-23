import os
import re
import csv
import json
import gzip
import shutil
import logging
import datetime
import subprocess
import luigi
import luigi.contrib.hdfs
import luigi.contrib.webhdfs
from prometheus_client import CollectorRegistry, Gauge
from tasks.common import state_file, report_file
from tasks.ingest.listings import CopyFileListToHDFS, csv_fieldnames
from lib.webhdfs import webhdfs

logger = logging.getLogger('luigi-interface')


class CurrentHDFSFileList(luigi.ExternalTask):
    """
    This is the file on HDFS to look for, generated by an independent task:
    """
    date = luigi.DateParameter(default=datetime.date.today())
    task_namespace = 'access'

    def output(self):
        return CopyFileListToHDFS(self.date).output()


class DownloadHDFSFileList(luigi.Task):
    """
    This downloads the HDFS file to a local copy for processing.
    """
    date = luigi.DateParameter(default=datetime.date.today())
    task_namespace = 'access'

    def requires(self):
        return CurrentHDFSFileList(self.date)

    def output(self):
        return state_file(None,'access-hdfs','all-files-list.csv', on_hdfs=False)

    def dated_state_file(self):
        return state_file(self.date,'access-hdfs','all-files-list.csv.gz', on_hdfs=False)

    def complete(self):
        # Check the dated file exists
        dated_target = self.dated_state_file()
        logger.info("Checking %s exists..." % dated_target.path)
        exists = dated_target.exists()
        logger.info("Got %s exists = %s..." % (dated_target.path, exists))
        if not exists:
            return False
        return True

    def run(self):
        # Use Luigi's helper to ensure the dated file only appears when all is well:
        with self.dated_state_file().temporary_path() as temp_output_path:

            # Download the file to the dated, compressed file (at a temporary path):
            logger.info("Downloading %s" % self.dated_state_file().path)
            client = webhdfs()
            with client.read(self.input().path) as f_in, open(temp_output_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            logger.info("Downloaded %s" % self.dated_state_file().path)

            # Also make an uncompressed version:
            logger.info("Decompressing %s" % self.dated_state_file().path)
            with gzip.open(temp_output_path, 'rb') as f_in, self.output().open('w') as f_out:
                shutil.copyfileobj(f_in, f_out)
            logger.info("Decompressed %s" % self.dated_state_file().path)


class ListWarcFileSets(luigi.Task):
    """
    Lists the WARCS and arranges them by date:
    """
    date = luigi.DateParameter(default=datetime.date.today())
    stream = luigi.Parameter(default='npld')

    def requires(self):
        return DownloadHDFSFileList(self.date, self.stream)

    #def complete(self):
    #    return False

    def output(self):
        return state_file(self.date, 'warc', 'warc-filesets.txt')

    def run(self):
        # Go through the data and assemble the resources for each crawl:
        filenames = []
        with self.input().open('r') as fin:
            reader = csv.DictReader(fin, fieldnames=csv_fieldnames)
            for item in reader:
                # Archive file names:
                file_path = item['filename']
                # Look at WARCS:
                if file_path.endswith('.warc.gz'):
                    filenames.append(file_path)

        # Sanity check:
        if len(filenames) == 0:
            raise Exception("No filenames generated! Something went wrong!")

        # Finally, emit the list of output files as the task output:
        filenames = sorted(filenames)
        counter = 0
        with self.output().open('w') as f:
            for output_path in filenames:
                if counter > 0:
                    if counter % 10000 == 0:
                        f.write('\n')
                    else:
                        f.write(' ')
                f.write('%s' % output_path)
                counter += 1


class ListWarcsByDate(luigi.Task):
    """
    Lists the WARCS with datestamps corresponding to a particular day. Defaults to yesterday.
    """
    date = luigi.DateParameter(default=datetime.date.today())

    def requires(self):
        # Get todays list:
        return DownloadHDFSFileList(self.date)

    def output(self):
        return state_file(self.date, 'warcs', 'warc-files-by-date.txt' )

    def run(self):
        # Build up a list of all WARCS, by day:
        by_day = {}
        with self.input().open('r') as fin:
            reader = csv.DictReader(fin, fieldnames=csv_fieldnames)
            for item in reader:
                # Archive file names:
                file_path = item['filename']
                # Only look at a subset:
                if file_path.startswith('/heritrix/output'):
                    # Look at WARCS:
                    if file_path.endswith('.warc.gz'):
                        m = re.search('^.*-([12][0-9]{16})-.*\.warc\.gz$', os.path.basename(file_path))
                        if m:
                            file_timestamp = datetime.datetime.strptime(m.group(1), "%Y%m%d%H%M%S%f").isoformat()
                        else:
                            # fall back on launch timestamp:
                            file_timestamp = item['modified_at']
                        file_datestamp = file_timestamp[0:10]

                        if file_datestamp not in by_day:
                            by_day[file_datestamp] = []

                        by_day[file_datestamp].append(item)
        # Write them out:
        filenames = []
        for datestamp in by_day:
            datestamp_output = state_file(None, 'warcs-by-day', '%s-%s-warcs-for-date.txt' % (datestamp,len(by_day[datestamp])))
            with datestamp_output.open('w') as f:
                f.write(json.dumps(by_day[datestamp], indent=2))

        # Emit the list of output files as the task output:
        self.file_count = len(filenames)
        with self.output().open('w') as f:
            for output_path in filenames:
                f.write('%s\n' % output_path)


class ListWarcsForDate(luigi.Task):
    """
    Lists the WARCS with datestamps corresponding to a particular day. Defaults to yesterday.
    """
    target_date = luigi.DateParameter(default=datetime.date.today() - datetime.timedelta(1))
    stream = luigi.Parameter(default='npld')
    date = luigi.DateParameter(default=datetime.date.today())

    file_count = None

    def requires(self):
        # Get todays list:
        return ListWarcsByDate(self.date)

    def output(self):
        datestamp = self.date.strftime("%Y-%m-%d")
        target_path = state_file(None, 'warcs-by-day', 'warcs-by-day-%s-*-warcs-for-date.txt' % datestamp).path
        print(os.system("ls %s" % target_path))
        return state_file(self.target_date, 'warcs', '%s-warc-files-for-date.txt' % self.file_count )

    def run(self):
        pass
