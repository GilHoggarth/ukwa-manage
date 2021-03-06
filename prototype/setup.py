import subprocess
from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

def get_version():
    try:
        return subprocess.check_output(['git', 'describe', '--tags', '--always']).strip()
    except:
        return "?.?.?"

setup(
    name='ukwa-manage',
    version=get_version(),
    packages=find_packages(),
    #install_requires=requirements, --Seems not to work well with remotes
    dependency_links=['http://github.com/ukwa/hapy/tarball/master#egg=hapy-heritrix'],
    include_package_data=True,
    license='Apache 2.0',
    long_description=open('README.md').read(),
    entry_points={
        'console_scripts': [
            'inject=ukwa.scripts.inject:main',
            'get-ids-from-hdfs=ukwa.lib.sip.ids:main',
            'generate-luigi-config=shepherd.lib.tasks.generate_config:main',
            'create-sip=ukwa.lib.lib.sip.creator:main',
            'movetohdfs=crawl.hdfs.movetohdfs:main',
            'w3act=ukwa.lib.w3act.w3act_cli:main',
            'pulse=ukwa.tasks.pulse:main'
        ]
    }
)
