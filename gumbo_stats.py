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
      'allocations', 'frees', 'bytes_allocated', 'bytes_freed',
      'high_water_mark', 'bytes_freed_during_parsing',
      'nodes', 'elements', 'text', 'whitespace', 'cdata', 'comments',
      'parser_inserted', 'reconstructed_formatting_element',
      'adoption_agency_cloned', 'adoption_agency_moved', 'foster_parented')
      ] + [(name + '_histogram', Histogram) for name in (
      'child', 'text', 'attribute', 'attribute_name', 'attribute_value')]

_parse_stats = _dll.parse_stats
_parse_stats.argtypes = [ctypes.c_char_p, ctypes.POINTER(Stats)]
_parse_stats.restype = None

def print_stat(key, obj):
  print('%s = %d' % (key, getattr(obj, key)))

def print_histogram(key, obj):
  histogram = getattr(obj, key + '_histogram')
  print('Max %s = %d.  |%s|' % (
      key, histogram.length - 1,
      ' '.join(str(val) for val in histogram.data[:10])))

def print_single_page_stats(text, stats):
  print('Text length = %d' % len(text))
  print_stat('parse_time_us', stats)
  print_stat('traversal_time_us', stats)
  print('')

  print_stat('allocations', stats)
  print_stat('bytes_allocated', stats)
  print_stat('high_water_mark', stats)
  print_stat('bytes_freed_during_parsing', stats)
  print('')

  print_stat('elements', stats)
  print_stat('text', stats)
  print_stat('whitespace', stats)
  print_stat('cdata', stats)
  print_stat('comments', stats)
  print('')

  print_histogram('child', stats)
  print_histogram('text', stats)
  print_histogram('attribute', stats)
  print_histogram('attribute_name', stats)
  print_histogram('attribute_value', stats)

def parse(text):
  stats = Stats()
  _parse_stats(text, ctypes.byref(stats))
  return stats

def parse_warc(filename):
  pass

def parse_file(filename):
  with open(filename) as infile:
    text = infile.read()
    stats = parse(text)
    print_single_page_stats(text, stats)

if __name__ == '__main__':
  filename = sys.argv[1]
  if filename.endswith('.warc.gz'):
    parse_warc(filename)
  else:
    parse_file(filename)
