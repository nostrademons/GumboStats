import ctypes
import gzip
import numpy
import os
import sys
import urlparse
import warc

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
      'parse_time_us', 'traversal_time_us', 'out_of_memory',
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

_destroy_stats = _dll.destroy_stats
_destroy_stats.argtypes = [ctypes.POINTER(Stats)]
_destroy_stats.restype = None

def print_stat(key, obj):
  print('%s = %d' % (key, getattr(obj, key)))

def print_histogram(key, obj):
  histogram = getattr(obj, key + '_histogram')
  len = min(12, histogram.length)
  print('Max %s = %d.  |%s|' % (
      key, histogram.length - 1,
      ' '.join(str(val) for val in histogram.data[:len])))

def print_single_page_stats(text, stats):
  print('Text length = %d' % len(text))
  print_stat('parse_time_us', stats)
  print_stat('traversal_time_us', stats)
  print('')

  print_stat('out_of_memory', stats)
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

class WARCStats(object):
  '''Computes stats over a whole WARCfile.

  The stats we're interested in include:
  * Quantiles for # of allocations over the corpus
  * Quantiles for bytes allocated
  * Quantiles for high-water-mark
  * Mean & stddev ratio of high-water-mark / bytes allocated.

  * Quantiles for # of nodes
  * Mean distribution for each type of node

  * Relationship between input size and bytes allocated
  * Relationship between input size and high-water mark
  * Relationship between input size and # nodes
  * Relationship between input size & parse/traversal time

  * Quantiles for the max values of children/attributes/textsize/etc, across
  documents.
  * Quantiles for each individual value of the above, 
  '''
  def __init__(self):
    self.parse_time = []
    self.traversal_time = []
    self.out_of_memory = 0
    self.allocations = []
    self.bytes_allocated = []
    self.high_water_mark = []
    self.num_nodes = []
    self.doc_length = []

    self.children = numpy.array([], dtype=int)
    self.text = numpy.array([], dtype=int)
    self.attribute = numpy.array([], dtype=int)
    self.attribute_name = numpy.array([], dtype=int)
    self.attribute_value = numpy.array([], dtype=int)

  def record_stats(self, text_length, stats):
    self.parse_time.append(stats.parse_time_us)
    self.traversal_time.append(stats.traversal_time_us * 1000)
    self.out_of_memory += stats.out_of_memory
    self.allocations.append(stats.allocations)
    self.bytes_allocated.append(stats.bytes_allocated)
    self.high_water_mark.append(stats.high_water_mark)
    self.num_nodes.append(stats.nodes)
    self.doc_length.append(text_length / 1000)

    def merge_histogram(merged, val):
      merged.resize(val.length, refcheck=False)
      merged += val.data[:val.length]

    merge_histogram(self.children, stats.child_histogram)
    merge_histogram(self.text, stats.text_histogram)
    merge_histogram(self.attribute, stats.attribute_histogram)
    merge_histogram(self.attribute_name, stats.attribute_name_histogram)
    merge_histogram(self.attribute_value, stats.attribute_value_histogram)

  def print_stats(self):
    def print_doc_average(label, value=None):
      value = getattr(self, label) if value is None else value
      print('%s: mean=%.2f, median=%.2f, 95th%%=%.2f, max=%.2f' % (
          label,
          numpy.mean(value),
          numpy.percentile(value, 50),
          numpy.percentile(value, 95),
          numpy.amax(value)))

    def ratio(numerator, denominator):
      label = '%s / %s' % (numerator, denominator)
      numerators = getattr(self, numerator)
      denominators = getattr(self, denominator)
      values = [float(a) / float(b) for a, b in zip(numerators, denominators)
          if b != 0]
      return label, values

    print_doc_average('parse_time')
    print_doc_average('traversal_time')
    print('out_of_memory: %d' % self.out_of_memory)
    print_doc_average('allocations')
    print_doc_average('bytes_allocated')
    print_doc_average('high_water_mark')
    print_doc_average('num_nodes')
    print('')

    print_doc_average(*ratio('num_nodes', 'doc_length'))
    print_doc_average(*ratio('parse_time', 'doc_length'))
    print_doc_average(*ratio('traversal_time', 'num_nodes'))
    print_doc_average(*ratio('bytes_allocated', 'high_water_mark'))
    print_doc_average(*ratio('high_water_mark', 'doc_length'))
    print_doc_average(*ratio('bytes_allocated', 'doc_length'))

    def print_histogram(label):
      value = getattr(self, label)
      total = numpy.sum(value)
      bins = range(1, total, total / 10)
      print('')
      print('%s: total=%d, max=%d' % (label, total, len(value)))
      print(' '.join(str(val) for val in value[:16]))
      print(' '.join(str(val) for val in
          numpy.digitize(bins, numpy.cumsum(value))))

    print_histogram('children')
    print_histogram('text')
    print_histogram('attribute')
    print_histogram('attribute_name')
    print_histogram('attribute_value')

def detect_charset(content_type):
    try:
        mime, charset = content_type.split('charset=')
        # Strip off the ; and optional trailing space.
        mime = mime.strip()[:-1]
    except ValueError:
        mime, charset = (content_type, 'ISO-8859-1')
    return mime, charset

def parse(text):
  stats = Stats()
  _parse_stats(text, ctypes.byref(stats))
  return stats

def parse_warc(filename):
  warc_stats = WARCStats()
  warcfile = warc.WARCFile(fileobj=gzip.GzipFile(fileobj=open(filename, 'rb')))
  warcfile.read_record()  # Skip warcinfo
  num_records = 0
  while 1:
    # Request
    if warcfile.read_record() is None:
      break
    # Body
    record = warcfile.read_record()
    headers, body = record.payload.read().split('\r\n\r\n', 1)
    headers = dict(
            line.split(': ', 1) for line in headers.split('\r\n')
            if ': ' in line)
    mime, charset = detect_charset(headers.get('Content-Type', 'text/html'))

    # Metadata
    warcfile.read_record()

    # Parsing
    if mime == 'text/html':
      try:
        stats = parse(body.decode(charset, 'replace').encode('utf-8'))
        warc_stats.record_stats(len(body), stats)
        _destroy_stats(stats)
        num_records += 1
      except LookupError:
        pass

  print('Num document = %d' % num_records)
  warc_stats.print_stats()

def parse_file(filename):
  with open(filename) as infile:
    text = infile.read()
    stats = parse(text)
    print_single_page_stats(text, stats)
    _destroy_stats(stats)

if __name__ == '__main__':
  filename = sys.argv[1]
  if filename.endswith('.warc.gz'):
    parse_warc(filename)
  else:
    parse_file(filename)
