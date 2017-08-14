import luigi
from shepherd.tasks.process.hadoop.hasher import GenerateHDFSSummaries
from shepherd.tasks.process.hadoop.turing import ListFilesToUploadToAzure


class DailyIngestTasks(luigi.WrapperTask):
    """
    Daily ingest tasks, should generally be a few hours ahead of the access-side tasks (below):
    """
    def requires(self):
        return [ GenerateHDFSSummaries() ]


class DailyAccessTasks(luigi.WrapperTask):
    """
    Daily access tasks. Depend on the ingest tasks, but will usually run from the access server,
    so can't be done in the one job.
    """
    def requires(self):
        return [ ListFilesToUploadToAzure() ]