"""
    Maintenance utility for tumblr blogs.

    :copyright: (c) 2015 by Mahmoud Hashemi
    :license: BSD, see LICENSE for more details.
"""

import sys
from setuptools import setup


__author__ = 'Mahmoud Hashemi'
__version__ = '0.0.5'
__contact__ = 'mahmoudrhashemi@gmail.com'
__url__ = 'https://github.com/mahmoud/grumblr'
__license__ = 'BSD'


if sys.version_info >= (3,):
    raise NotImplementedError("grumblr Python 3 support en route to your location")


if __name__ == '__main__':
    setup(name='grumblr',
          version=__version__,
          description="Maintenance utility for tumblr blogs.",
          long_description=__doc__,
          author=__author__,
          author_email=__contact__,
          url=__url__,
          packages=['grumblr'],
          install_requires=['ashes==17.0.0',
                            'boltons==17.1.0',
                            'gevent==1.2.1',
                            'progressbar==2.3',
                            'PyTumblr==0.0.6',
                            'PyYAML==3.11'],
          include_package_data=True,
          zip_safe=False,
          license=__license__,
          platforms='any',
          classifiers=[
              'Topic :: Software Development :: Libraries',
              'Programming Language :: Python :: 2.7', ])
