#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 12 18:22:03 2022

@author: bwimmer
"""

import unittest
from tomotools.commands import preprocessing_reconstruction

# TODO: implement test mdoc reading
# TODO: implement test anchor / batch detection
# TODO: implement test for batchfile -> should not fail on empty line // should not change NoneType when file not in list
# TODO: implement test for previous


class Testing(unittest.TestCase):
    def test_reconstruct(self):
        # Tests whether reconstruct command works across different detector sizes.

        params = {
            "move": False,
            "local": False,
            "extra_thickness": 0,
            "bin": 1,
            "sirt": 8,
            "keep_ali_stack": 1,
            "previous": None,
            "batch_file": None,
        }

        testfiles = [
            "testfiles/UniHD_K3_2206.mrc",
            "testfiles/UZH_K2_2111.mrc",
            "testfiles/UZH_K2_2207.mrc",
            "testfiles/UZH_K3_2207.mrc",
        ]

        for testfile in testfiles:
            with self.subTest(testfiles):
                reconstruction = tomography.reconstruct(**params, input_files=testfile)

                self.assertRegexpMatches()
                self.assertNotIn(
                    reconstruction,
                )


if __name__ == "__main__":
    unittest.main()
