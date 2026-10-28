#include <stdlib.h>
static void (*event_callback)(int);
void *resource_fixture_create(void (*callback)(int)) {
  event_callback=callback;
  return malloc(8);
}
void resource_fixture_destroy(void *object) {
  if(event_callback)event_callback(1);
  free(object);
}
__attribute__((destructor)) static void resource_fixture_unload(void) {
  if(event_callback)event_callback(2);
}
