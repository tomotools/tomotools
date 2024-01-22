"""File for future tests of alignment, reconstructions, etc."""


# TODO: implement test mdoc reading
# TODO: implement test anchor / batch detection
# TODO: implement test for batchfile -> should not fail on empty line
# TODO: implement test for batchfile -> should not change NoneType when file not in list
# TODO: implement test for previous


#class Testing(unittest.TestCase):
#     """Testing class for tomotools reconstruct."""

#     def test_reconstruct(self):
#         """Test reconstruction itself."""
#         # Tests whether reconstruct command works across different detector sizes.

#         params = {
#             "move": False,
#             "local": False,
#             "extra_thickness": 0,
#             "bin": 1,
#             "sirt": 8,
#             "keep_ali_stack": 1,
#             "previous": None,
#             "batch_file": None,
#         }

#         testfiles = [
#             "testfiles/UniHD_K3_2206.mrc",
#             "testfiles/UZH_K2_2111.mrc",
#             "testfiles/UZH_K2_2207.mrc",
#             "testfiles/UZH_K3_2207.mrc",
#         ]

#         for testfile in testfiles:
#             with self.subTest(testfiles):
#                 reconstruction = Tomogram.from_tiltseries(testfile)

#                 self.assertRegex()
#                 self.assertNotIn(
#                     reconstruction,
#                 )


# if __name__ == "__main__":
#     unittest.main()
