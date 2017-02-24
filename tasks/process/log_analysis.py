import os
import json
import hashlib
import logging
import threading
import luigi.contrib.hdfs
import luigi.contrib.hadoop

from tasks.crawl.h3.crawl_job_tasks import CrawlFeed
from tasks.process.hadoop.crawl_summary import ScanForOutputs
from tasks.process.log_analysis_hadoop import AnalyseLogFile
from tasks.process.extract.documents import ExtractDocumentAndPost
from luigi.contrib.hdfs.format import Plain, PlainDir

logger = logging.getLogger('luigi-interface')

HDFS_PREFIX = os.environ.get("HDFS_PREFIX", "")
WAYBACK_PREFIX = os.environ.get("WAYBACK_PREFIX", "http://localhost:9080/wayback")

LUIGI_STATE_FOLDER = os.environ['LUIGI_STATE_FOLDER']
ACT_URL = os.environ['ACT_URL']
ACT_USER = os.environ['ACT_USER']
ACT_PASSWORD = os.environ['ACT_PASSWORD']


class LogFilesForJobLaunch(luigi.ExternalTask):
    """
    On initialisation, looks up all logs current on HDFS for a particular job.

    Emits list of files to be processed.

    No run() as depends on external processes that produce the logs.
    """
    task_namespace = 'scan'
    job = luigi.Parameter()
    launch_id = luigi.Parameter()

    def output(self):
        outputs = []
        # Get HDFS client:
        client = luigi.contrib.hdfs.get_autoconfig_client()
        parent_path = "/heritrix/output/logs/%s/%s" % (self.job, self.launch_id)
        for listed_item in client.listdir(parent_path):
            # Oddly, depending on the implementation, the listed_path may be absolute or basename-only, so fix here:
            item = os.path.basename(listed_item)
            item_path = os.path.join(parent_path, item)
            if item.endswith(".lck"):
                logger.error("Lock file should be be present on HDFS! %s" % (item, item_path))
                pass
            elif item.startswith("crawl.log"):
                outputs.append(luigi.contrib.hdfs.HdfsTarget(path=item_path, format=Plain))
                #logger.debug("Including %s" % item)
            else:
                pass
                #logger.debug("Skipping %s" % item)
        # Return the logs to be processed:
        return outputs


class SyncToHdfs(luigi.Task):
    """
    Designed to sync a single file up onto HDFS - intended for temp files while running jobs.
    """
    source_path = luigi.Parameter()
    target_path = luigi.Parameter()
    overwrite = luigi.BoolParameter(default=False)

    def complete(self):
        # Read local:
        local = luigi.LocalTarget(path=self.source_path)
        with local.open('r') as reader:
            local_hash = hashlib.sha512(reader.read()).hexdigest()
            logger.info("LOCAL HASH: %s" % local_hash)
        # Read from HDFS
        client = luigi.contrib.hdfs.get_autoconfig_client(threading.local())
        if not client.exists(self.target_path):
            return False
        with client.client.read(self.target_path) as reader:
            hdfs_hash = hashlib.sha512(reader.read()).hexdigest()
            logger.info("HDFS HASH: %s" % hdfs_hash)

        # If they match, we are good:
        return hdfs_hash == local_hash

    def output(self):
        return luigi.contrib.hdfs.HdfsTarget(path=self.target_path, format=Plain)

    def run(self):
        client = luigi.contrib.hdfs.get_autoconfig_client(threading.local())
        client.upload(hdfs_path=self.output().path, local_path=self.source_path, overwrite=self.overwrite)


class AnalyseAndProcessDocuments(luigi.Task):
    task_namespace = 'analyse'
    job = luigi.Parameter()
    launch_id = luigi.Parameter()
    log_path = luigi.Parameter()
    targets_path = luigi.Parameter()
    from_hdfs = luigi.BoolParameter(default=False)

    def requires(self):
        return AnalyseLogFile(self.job, self.launch_id, self.log_file, self.hdfs_targets, True)

    def output(self):
        return luigi.LocalTarget(
            '{}/documents/posted-{}-{}-{}'.format(LUIGI_STATE_FOLDER, self.job, self.launch_id, os.path.basename(self.log_path)))

    def run(self):
        # Loop over documents discovered, and attempt to post to W3ACT:
        with self.output().open() as out_file:
            with self.input().open() as in_file:
                counter = 0
                tasks = []
                for line in in_file:
                    prefix, docjson = line.strip().split("\t", 1)
                    if prefix == "DOCUMENT":
                        doc = json.loads(docjson)
                        out_file.write("%s\n" % json.dumps(doc))
                        tasks.append(ExtractDocumentAndPost(self.job, self.launch_id, doc, doc["source"]))
                        counter += 1
                        # Group tasks into bunches of five:
                        if counter%5 == 0:
                            yield tasks
                            tasks = []


class GenerateCrawlLogReports(luigi.Task):
    """
    Via required tasks, launched M-R job to process crawl logs.

    Then runs through output documents and attempts to post them to W3ACT.
    """
    task_namespace = 'report'
    job = luigi.Parameter()
    launch_id = luigi.Parameter()
    extract_documents = luigi.BoolParameter(default=False)

    def requires(self):
        return LogFilesForJobLaunch(self.job, self.launch_id)

    def output(self):
        logs_count = len(self.input())
        return luigi.LocalTarget(
            '{}/logs/reported-{}-{}-{}'.format(LUIGI_STATE_FOLDER, self.job, self.launch_id, logs_count))

    def run(self):
        # Set up necessary data:
        feed = yield CrawlFeed(self.job)
        hdfs_targets = yield SyncToHdfs(feed.path, '%s-crawl-feed.json' % self.job, overwrite=True)

        # Build up a list of tasks, one for each log file:
        tasks = []
        for log_file in self.input():
            if self.extract_documents:
                tasks.append(AnalyseAndProcessDocuments(self.job, self.launch_id, log_file.path, hdfs_targets.path, True))
            else:
                tasks.append(AnalyseLogFile(self.job, self.launch_id, log_file.path, hdfs_targets.path, True))
        yield tasks


class ScanForLogs(ScanForOutputs):
    """
    This task scans the output folder for jobs and instances of those jobs, looking for crawls logs.
    """
    task_namespace = 'scan'
    scan_name = 'logs'

    def process_output(self, job, launch):
        yield GenerateCrawlLogReports(job, launch)


if __name__ == '__main__':
    luigi.run(['report.GenerateCrawlLogReports', '--job', 'weekly', '--launch-id', '20170220090024', '--local-scheduler'])
