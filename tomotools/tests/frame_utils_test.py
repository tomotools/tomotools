"""Test for batch-prepare-tiltseries."""

# TODO: test RotationAndFlip (not in file, right output)
# TODO: test subframe right properties
# TODO: assert Subframe
# TODO: implement test reordering (vs. newstack --reorder 1 output)

import unittest

from tomotools.utils.micrograph import sem2mc2


class batch_prepare_test(unittest.TestCase):
    """test batch-prepare-tiltseries."""

    def test_sem2mc2(self):
        """Tests whether RotationAndFlip is properly converted to MC2."""
        test_inputs = [0, 3, 5, 6]
        test_results = [[0,0], [3,0], [1,2], [2,2]]

        for challenge, response in zip(test_inputs, test_results):
            self.assertTrue(sem2mc2(challenge) == response)

if __name__ == "__main__":
     unittest.main()
