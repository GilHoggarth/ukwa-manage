import os
import logging
import posixpath
import luigi.contrib.hdfs
import luigi.contrib.webhdfs
from luigi.contrib.postgres import PostgresTarget, CopyToTable
from lib.webhdfs import WebHdfsPlainFormat
from prometheus_client import CollectorRegistry, push_to_gateway, Gauge
from tasks.metrics import record_task_outcome

LOCAL_STATE_FOLDER = os.environ.get('LOCAL_STATE_FOLDER', '/var/task-state')
HDFS_STATE_FOLDER = os.environ.get('HDFS_STATE_FOLDER','/9_processing/task-state/')

logger = logging.getLogger('luigi-interface')


def state_file(date, tag, suffix, on_hdfs=False, use_gzip=False, use_webhdfs=False):
    # Set up the state folder:
    state_folder = LOCAL_STATE_FOLDER
    pather = os.path
    if on_hdfs:
        pather = posixpath
        state_folder = HDFS_STATE_FOLDER

    # build the full path:
    if date is None:
        full_path = pather.join(
            str(state_folder),
            tag,
            "%s-%s" % (tag,suffix))
    elif isinstance(date, str):
        full_path = pather.join(
            str(state_folder),
            tag,
            date,
            "%s-%s-%s" % (date,tag,suffix))
    else:
        full_path = pather.join(
            str(state_folder),
            tag,
            date.strftime("%Y-%m"),
            '%s-%s-%s' % (date.strftime("%Y-%m-%d"), tag, suffix))

    # Replace any awkward characters
    full_path = full_path.replace(":","_")

    if on_hdfs:
        if use_webhdfs:
            return luigi.contrib.hdfs.HdfsTarget(path=full_path, format=WebHdfsPlainFormat(use_gzip=use_gzip))
        else:
            return luigi.contrib.hdfs.HdfsTarget(path=full_path, format=luigi.contrib.hdfs.PlainFormat())
    else:
        return luigi.LocalTarget(path=full_path)


# --------------------------------------------------------------------------
# These helpers help set up database targets for fine-grained task outputs
# --------------------------------------------------------------------------

class CopyToTableInDB(CopyToTable):
    """
    Abstract class that fixes which tables are used
    """
    host = 'access'
    database = 'access_task_state'
    user = 'access'
    password = 'access'

    def output(self):
        """
        Returns a PostgresTarget representing the inserted dataset.
        """
        return taskdb_target(self.table,self.update_id)


class CopyToTableInIngestDB(CopyToTable):
    """
    Abstract class that fixes which tables are used
    """
    host = 'ingest'
    database = 'ingest_task_state'
    user = 'ingest'
    password = 'ingest'

    def output(self):
        """
        Returns a PostgresTarget representing the inserted dataset.
        """
        return taskdb_target(self.table,self.update_id, kind='ingest')

# --------------------------------------------------------------------------
# This general handler reports task failure and success, for each task
# family (class name) and namespace.
#
# For some specific classes, additional metrics are computed.
# --------------------------------------------------------------------------


@luigi.Task.event_handler(luigi.Event.FAILURE)
def notify_any_failure(task, exception):
    # type: (luigi.Task) -> None
    """
       Will be called directly after a successful execution
       and is used to update any relevant metrics
    """

    # Where to store the metrics:
    registry = CollectorRegistry()

    # Generate metrics:
    record_task_outcome(registry, task, 0, luigi.Event.FAILURE)

    # POST to Prometheus Push Gateway:
    if os.environ.get("PUSH_GATEWAY"):
        push_to_gateway(os.environ.get("PUSH_GATEWAY"), job=task.get_task_family(), registry=registry)
    else:
        logger.error("No metrics gateway configured!")


@luigi.Task.event_handler(luigi.Event.SUCCESS)
def celebrate_any_success(task):
    """Will be called directly after a successful execution
       of `run` on any Task subclass (i.e. all luigi Tasks)
    """

    # Where to store the metrics:
    registry = CollectorRegistry()

    # Generate metrics:
    record_task_outcome(registry, task, 1, luigi.Event.SUCCESS)

    # POST to Prometheus Push Gateway:
    if os.environ.get("PUSH_GATEWAY"):
        push_to_gateway(os.environ.get("PUSH_GATEWAY"), job=task.get_task_family(), registry=registry)
    else:
        logger.error("No metrics gateway configured!")


@luigi.Task.event_handler(luigi.Event.PROCESSING_TIME)
def record_processing_time(task, processing_time):
    """Record the processing time of every task."""
    logger.info("Got %s processing time %s" % (task.task_namespace, str(processing_time)))

    # Where to store the metrics:
    registry = CollectorRegistry()

    # Disable pylint warnings due to it not picking up decorators:
    # pylint: disable=E1101,E1120,E1123,E1124
    
    # Generate metrics:
    g = Gauge('ukwa_task_processing_time',
              'Processing time of a task, in seconds.',
               labelnames=['task_namespace'], registry=registry)
    g.labels(task_namespace=task.task_namespace).set(processing_time)

    # POST to Prometheus Push Gateway:
    if os.environ.get("PUSH_GATEWAY"):
        push_to_gateway(os.environ.get("PUSH_GATEWAY"), job=task.get_task_family(), registry=registry)
    else:
        logger.error("No metrics gateway configured!")
