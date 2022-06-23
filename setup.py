from setuptools import setup

setup(
    name='Tomotools',
    version='0.1.0',
    packages=['tomotools', 'tomotools.commands', 'tomotools.utils'],
    install_requires=[
        'Click',
        'numpy',
        'pandas',
        'mrcfile',
        'emfile',
        'dynamotable',
        'tensorflow',
        'cryoCARE',
        'packaging',
    ],
    entry_points={
        'console_scripts': [
            'tomotools = tomotools:tomotools',
        ],
    },
)
