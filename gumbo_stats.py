import ctypes
import sys

def parse_warc(filename):
  pass

def parse_file(filename):
  with open(filename) as infile:
    text = infile.read()
    print(text)

if __name__ == '__main__':
  filename = sys.argv[1]
  if filename.endswith('.warc.gz'):
    parse_warc(filename)
  else:
    parse_file(filename)
