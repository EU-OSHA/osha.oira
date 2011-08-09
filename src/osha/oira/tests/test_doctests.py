import doctest
import glob
import os.path
import unittest
from Testing.ZopeTestCase import FunctionalDocFileSuite
from base import OiRAFunctionalTestCase

def test_suite():
    location=os.path.dirname(__file__) or "."
    doctests=["stories/"+os.path.basename(test)
             for test in glob.glob(os.path.join(location, "stories", "*.txt"))]

    options=doctest.REPORT_ONLY_FIRST_FAILURE | \
            doctest.ELLIPSIS | \
            doctest.NORMALIZE_WHITESPACE

    suites=[FunctionalDocFileSuite(test,
                                   optionflags=options,
                                   test_class=OiRAFunctionalTestCase,
                                   module_relative=True,
                                   package="osha.oira.tests",
                                   encoding="utf-8")
            for test in doctests]
    return unittest.TestSuite(suites)

