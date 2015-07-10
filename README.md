python-legal-deposit-sip
==============

Provides a `SipCreator` which can produce a `METS` file for Heritrix jobs. For example, SIPs created for the WDI ingest stream are created via:

    sip_dir = "%s/%s" % (settings.SIP_ROOT, job)
    s = sip.SipCreator(jobs=["daily/20150708110924"], jobname="daily/20150708110924", dummy=False)
    if s.verifySetup():
        s.processJobs()
        s.createMets()
        filename = os.path.basename(job)
        os.makedirs(sip_dir)
        with open( "%s/%s.xml" % (sip_dir, filename , "wb") as o:
            s.writeMets(o)
        s.bagit(sip_dir)
    else:
        raise Exception("Could not verify SIP for %s" % job)

Note that it relies on proper configuration via the `settings` package. Largely the settings should be self-explanatory, however, two of note are:

    ZIP="/opt/zip30/bin/zip -jg"
    UNZIP="/opt/unzip60/bin/unzip"

The default version of `zip` and `unzip` deployed with RedHat do not handle ZIP files sufficiently large to cope with Domain Crawl SIPs. Thus we require a separate installation.

