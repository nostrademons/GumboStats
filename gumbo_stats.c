// Copyright 2015 Jonathan Tang. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifdef __cplusplus
extern "C" {
#endif

#include <assert.h>
#include <malloc.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include "gumbo.h"

typedef struct {
  unsigned int length;
  unsigned int* data;
} Histogram;

typedef struct {
  unsigned int parse_time_us;
  unsigned int traversal_time_us;

  unsigned int allocations;
  unsigned int frees;
  unsigned int bytes_allocated;
  unsigned int bytes_freed;
  unsigned int high_water_mark;
  unsigned int bytes_freed_during_parsing;

  unsigned int nodes;
  unsigned int elements;
  unsigned int text;
  unsigned int whitespace;
  unsigned int cdata;
  unsigned int comments;

  unsigned int parser_inserted;
  unsigned int reconstructed_formatting_element;
  unsigned int adoption_agency_cloned;
  unsigned int adoption_agency_moved;
  unsigned int foster_parented;

  Histogram child_histogram;
  Histogram text_histogram;
  Histogram attribute_histogram;
  Histogram attribute_name_histogram;
  Histogram attribute_value_histogram;
} GumboStats;

typedef struct {
  unsigned int children;
  unsigned int text;
  unsigned int attribute;
  unsigned int attribute_name;
  unsigned int attribute_value;
} GumboMax;

static inline void set_max(unsigned int new_val, unsigned int* current) {
  *current = new_val > *current ? new_val : *current;
}

static inline void incr_histogram(unsigned int val, Histogram* histogram) {
  assert(histogram->data != NULL);
  if (val >= histogram->length || val < 0) {
    printf("Value %d out of histogram size %d", val, histogram->length);
    return;
  }
  ++histogram->data[val];
}

// gumbo_vector_init isn't exposed publicly, and in any case we want to avoid
// going through the allocator when we initialize our histograms so we don't
// pollute our allocation stats.
static inline void histogram_init(unsigned int size, Histogram* vector) {
  vector->length = size + 1;
  vector->data = malloc(sizeof(unsigned int) * vector->length);
  memset(vector->data, 0, sizeof(unsigned int) * vector->length);
}

// Memory allocation functions

static void* stat_collecting_malloc(void* userdata, size_t size) {
  GumboStats* stats = (GumboStats*) userdata;
  stats->allocations += 1;
  stats->bytes_allocated += size;
  set_max(stats->bytes_allocated - stats->bytes_freed, &stats->high_water_mark);
  return malloc(size);
}

static void stat_collecting_free(void* userdata, void* obj) {
  GumboStats* stats = (GumboStats*) userdata;
  stats->frees += 1;
  stats->bytes_freed += malloc_usable_size(obj);
  free(obj);
}

// First tree traversal; this just collects maximum vector lengths for
// children/attributes/text nodes so we can allocate histograms later.
void find_max(GumboNode* node, GumboMax* max) {
  switch(node->type) {
    case GUMBO_NODE_DOCUMENT:
      {
        GumboDocument* doc = &node->v.document;
        set_max(doc->children.length, &max->children);
        set_max(strlen(doc->name), &max->text);
        set_max(strlen(doc->public_identifier), &max->text);
        set_max(strlen(doc->system_identifier), &max->text);
        for (int i = 0; i < doc->children.length; ++i) {
          find_max(doc->children.data[i], max);
        }
        return;
      }
    case GUMBO_NODE_ELEMENT:
      {
        GumboElement* elem = &node->v.element;
        set_max(elem->children.length, &max->children);
        set_max(elem->attributes.length, &max->attribute);
        for (int i = 0; i < elem->attributes.length; ++i) {
          GumboAttribute* attr = elem->attributes.data[i];
          set_max(strlen(attr->name), &max->attribute_name);
          set_max(strlen(attr->value), &max->attribute_value);
        }
        for (int i = 0; i < elem->children.length; ++i) {
          find_max(elem->children.data[i], max);
        }
        return;
      }
    case GUMBO_NODE_TEXT:
    case GUMBO_NODE_WHITESPACE:
    case GUMBO_NODE_COMMENT:
    case GUMBO_NODE_CDATA:
      set_max(strlen(node->v.text.text), &max->text);
      return;
  }
}

// Second tree traversal; once we've had the GumboStats object fully
// initialized, we recurse over the tree again to collect more detailed stats.
void collect_stats(GumboNode* node, GumboStats* stats) {
  ++stats->nodes;
  if (node->parse_flags & GUMBO_INSERTION_BY_PARSER) {
    ++stats->parser_inserted;
  }
  if (node->parse_flags & GUMBO_INSERTION_RECONSTRUCTED_FORMATTING_ELEMENT) {
    ++stats->reconstructed_formatting_element;
  }
  if (node->parse_flags & GUMBO_INSERTION_ADOPTION_AGENCY_CLONED) {
    ++stats->adoption_agency_cloned;
  }
  if (node->parse_flags & GUMBO_INSERTION_ADOPTION_AGENCY_MOVED) {
    ++stats->adoption_agency_moved;
  }
  if (node->parse_flags & GUMBO_INSERTION_FOSTER_PARENTED) {
    ++stats->foster_parented;
  }
  switch(node->type) {
    case GUMBO_NODE_DOCUMENT:
      {
        GumboDocument* doc = &node->v.document;
        incr_histogram(doc->children.length, &stats->child_histogram);
        incr_histogram(strlen(doc->name), &stats->text_histogram);
        incr_histogram(strlen(doc->public_identifier), &stats->text_histogram);
        incr_histogram(strlen(doc->system_identifier), &stats->text_histogram);
        for (int i = 0; i < doc->children.length; ++i) {
          collect_stats(doc->children.data[i], stats);
        }
        return;
      }
    case GUMBO_NODE_ELEMENT:
      {
        GumboElement* elem = &node->v.element;
        incr_histogram(elem->children.length, &stats->child_histogram);
        incr_histogram(elem->attributes.length, &stats->attribute_histogram);

        ++stats->elements;

        for (int i = 0; i < elem->attributes.length; ++i) {
          GumboAttribute* attr = elem->attributes.data[i];
          incr_histogram(strlen(attr->name), &stats->attribute_name_histogram);
          incr_histogram(strlen(attr->value), &stats->attribute_value_histogram);
        }
        for (int i = 0; i < elem->children.length; ++i) {
          collect_stats(elem->children.data[i], stats);
        }
        return;
      }
    case GUMBO_NODE_TEXT:
      ++stats->text;
      incr_histogram(strlen(node->v.text.text), &stats->text_histogram);
      return;
    case GUMBO_NODE_WHITESPACE:
      ++stats->whitespace;
      incr_histogram(strlen(node->v.text.text), &stats->text_histogram);
      return;
    case GUMBO_NODE_COMMENT:
      ++stats->comments;
      incr_histogram(strlen(node->v.text.text), &stats->text_histogram);
      return;
    case GUMBO_NODE_CDATA:
      ++stats->cdata;
      incr_histogram(strlen(node->v.text.text), &stats->text_histogram);
      return;
  }
}

void parse_stats(const char* input, GumboStats* stats) {
  memset(stats, 0, sizeof(GumboStats));
  GumboOptions options = kGumboDefaultOptions;
  options.allocator = stat_collecting_malloc;
  options.deallocator = stat_collecting_free;
  options.userdata = stats;
  
  clock_t start_time = clock();
  GumboOutput* output = gumbo_parse_with_options(
    &options, input, strlen(input));
  clock_t end_time = clock();
  stats->parse_time_us = 1000000 * (end_time - start_time) / CLOCKS_PER_SEC;
  stats->bytes_freed_during_parsing = stats->bytes_freed;

  GumboMax max;
  memset(&max, 0, sizeof(GumboMax));
  start_time = clock();
  find_max(output->document, &max);
  end_time = clock();
  stats->traversal_time_us =
      1000000 * (end_time - start_time) / CLOCKS_PER_SEC;

  histogram_init(max.children, &stats->child_histogram);
  histogram_init(max.text, &stats->text_histogram);
  histogram_init(max.attribute, &stats->attribute_histogram);
  histogram_init(max.attribute_name, &stats->attribute_name_histogram);
  histogram_init(max.attribute_value, &stats->attribute_value_histogram);

  collect_stats(output->document, stats);
  gumbo_destroy_output(&options, output);
}

void destroy_stats(GumboStats* stats) {
  free(stats->child_histogram.data);
  free(stats->text_histogram.data);
  free(stats->attribute_histogram.data);
  free(stats->attribute_name_histogram.data);
  free(stats->attribute_value_histogram.data);
}

static void read_file(FILE* fp, char** output) {
  struct stat filestats;
  int fd = fileno(fp);
  fstat(fd, &filestats);
  int length = filestats.st_size;
  *output = malloc(length + 1);
  int start = 0;
  int bytes_read;
  while ((bytes_read = fread(*output + start, 1, length - start, fp))) {
    start += bytes_read;
  }
  (*output)[length] = '\0';
}

int main(int argc, char** argv) {
  if (argc != 2) {
    printf("Usage: gumbo_stats <html filename>.\n");
    exit(EXIT_FAILURE);
  }
  const char* filename = argv[1];

  FILE* fp = fopen(filename, "r");
  if (!fp) {
    printf("File %s not found!\n", filename);
    exit(EXIT_FAILURE);
  }

  char* input;
  read_file(fp, &input);
  GumboStats stats;
  parse_stats(input, &stats);
  printf("Elements = %d\n", stats.elements);
}

#ifdef __cplusplus
}
#endif
