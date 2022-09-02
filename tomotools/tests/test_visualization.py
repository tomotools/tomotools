import unittest
import numpy as np
import csv

#from tomotools.commands import visualization
from tomotools.utils import mathutil

class Testing(unittest.TestCase):
    def test_ctf1d(self):
        # Tests whether ctf1d returns correct ctf (compared to original implementation on https://github.com/dtegunov/tom_deconv
       
       params = {'length': 128, 'pixelsize': 10e-10, 'voltage': 300e3, 'cs': 2.7e-3, 'defocus': -6e-6, 'amplitude': 0.07, 'phaseshift': 0, 'bfactor': 0}
       
       result = np.array([0.07,0.070565,0.072259,0.075083,0.079035,0.084114,0.090319,0.097648,0.1061,0.11566,0.12634,0.13813,0.15102,0.165,0.18006,0.19618,0.21337,
                          0.23158,0.25082,0.27104,0.29223,0.31435,0.33737,0.36125,0.38593,0.41138,0.43752,0.46431,0.49166,0.51951,0.54776,0.57632,0.6051,0.63399,
                          0.66287,0.69161,0.72008,0.74814,0.77563,0.80241,0.82829,0.85311,0.87668,0.89881,0.9193,0.93796,0.95457,0.96893,0.98083,0.99005,0.99638,
                          0.99961,0.99954,0.99597,0.98871,0.97759,0.96243,0.9431,0.91947,0.89143,0.85889,0.82182,0.78018,0.73399,0.6833,0.62819,0.56881,0.50532,
                          0.43795,0.36697,0.2927,0.21552,0.13584,0.054134,-0.029063,-0.11318,-0.19761,-0.28168,-0.36469,-0.44591,-0.52457,-0.59989,-0.67106,-0.7373,
                          -0.79778,-0.85173,-0.89839,-0.93703,-0.96698,-0.98763,-0.99842,-0.99893,-0.98878,-0.96775,-0.93571,-0.89268,-0.83883,-0.77447,-0.70006,
                          -0.61624,-0.5238,-0.42369,-0.31703,-0.20508,-0.089245,0.028946,0.14785,0.26574,0.38082,0.49125,0.59518,0.6908,0.77633,0.85011,0.91058,
                          0.95637,0.9863,0.99943,0.99508,0.9729,0.93282,0.87515,0.80055,0.71002,0.60496,0.48711,0.35855,0.22165],dtype = 'float64')
       
       self.assertTrue(np.allclose(mathutil.tom_ctf1d(**params), result, rtol = 1e-3))

    def test_wiener(self):
        # Test whether Wiener filter is correctly constructed (compared to original implementation)
        
        cases = [{'in': {'angpix': 10, 'defocus': 6, 'snrfalloff': 1, 'deconvstrength': 1, 'hpnyquist': 0.02, 'phaseflipped': False, 'phaseshift': 0},
                 'result': 'testfiles/Wiener_case1.csv'},
                 {'in': {'angpix': 10, 'defocus': 6, 'snrfalloff': 1.2, 'deconvstrength': 0.67, 'hpnyquist': 0.02, 'phaseflipped': True, 'phaseshift': 0},
                   'result': 'testfiles/Wiener_case2.csv'}]

        for case in cases:
            with self.subTest(cases):
                with open(case['result'], mode = 'r') as file:
                    result = csv.reader(file)
                    result = list(result)[0]
                    result = [float(ele) for ele in result]
                
                self.assertTrue(np.allclose(mathutil.wiener(**case['in']),result,rtol = 1e-3))
                

if __name__ == '__main__':
    unittest.main()        
