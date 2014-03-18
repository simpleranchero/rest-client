from setuptools import setup, find_packages
import sys, os

version = '0.1'

setup(name='rest-client',
      version=version,
      description="Simple python",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='REST client',
      author='Eugene Konstantinov',
      author_email='eikohct@gmail.com',
      url='https://github.com/simpleranchero',
      license='GPL2',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          'requests',
	  'pytest',
	  'httpretty'
      ],
      entry_points="""
      # -*- Entry points: -*-
      """,
      )
