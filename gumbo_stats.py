import ctypes
import os
import sys

_dll_file = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), 'libgumbostats.so')
_dll = ctypes.cdll.LoadLibrary(_dll_file)

class Histogram(ctypes.Structure):
  _fields_ = [
      ('length', ctypes.c_uint),
      ('data', ctypes.POINTER(ctypes.c_uint))
  ]

class Stats(ctypes.Structure):
  _fields_ = [(name, ctypes.c_uint) for name in (
      'parse_time_us', 'traversal_time_us',
      'allocations', 'frees', 'bytes_allocated', 'frees_during_parsing',
      'nodes', 'elements', 'text', 'whitespace', 'cdata', 'comments',
      'parser_inserted', 'reconstructed_formatting_element',
      'adoption_agency_cloned', 'adoption_agency_moved', 'foster_parented')
      ] + [(name + '_histogram', Histogram) for name in (
      'child', 'text', 'attribute', 'attribute_name', 'attribute_value')]

_parse_stats = _dll.parse_stats
_parse_stats.argtypes = [ctypes.c_char_p, ctypes.POINTER(Stats)]
_parse_stats.restype = None

def parse(text):
  stats = Stats()
  _parse_stats("<div>Text</div>", ctypes.byref(stats))
  return stats

def parse_warc(filename):
  pass

def parse_file(filename):
  with open(filename) as infile:
    text = infile.read()
    stats = parse(text)

    print('Max text length=%d' % (stats.text_histogram.length - 1))
    print('Max children length=%d' % (stats.child_histogram.length - 1))

if __name__ == '__main__':
  filename = sys.argv[1]
  if filename.endswith('.warc.gz'):
    parse_warc(filename)
  else:
    parse_file(filename)
