from setuptools import setup

setup(
    name='Tomotools',
    version='0.1.0',
    py_modules=['tomotools', 'mdocfile', 'util'],
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
