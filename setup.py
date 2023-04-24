from setuptools import setup

setup(
    name='Tomotools',
    version='0.2.3',
    packages=['tomotools', 'tomotools.commands', 'tomotools.utils'],
    install_requires=[
        'Click',
        'numpy',
        'pandas',
        'mrcfile',
        'emfile',
        'dynamotable',
        'tensorflow==2.4',
        'cryoCARE',
        'packaging',
    ],
    entry_points={
        'console_scripts': [
            'tomotools = tomotools:tomotools',
        ],
    },
)
