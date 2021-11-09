from setuptools import setup

setup(
    name='ai2021',
    version='1.1.1',    
    description='A python3 party that places random bids with sufficient utility',
    url='https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWeb',
    author='W.Pasman',
    packages=['ai2021', 'ai2021.group33'],
    install_requires=[ "geniusweb@https://tracinsy.ewi.tudelft.nl/pubtrac/GeniusWebPython/export/68/geniuswebcore/dist/geniusweb-1.1.1.tar.gz"],
    py_modules=['party']
)