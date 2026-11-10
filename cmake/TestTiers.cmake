# Test labels are metadata: preserve commands, budgets, fixture relationships,
# platform conditions and the complete unfiltered CTest registry.
include_guard(GLOBAL)
set(NEX_TEST_TIER_POLICY "${CMAKE_CURRENT_LIST_DIR}/test-tiers.json")
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -I -B "${CMAKE_CURRENT_LIST_DIR}/../tools/ctest_tiers.py"
          --policy "${NEX_TEST_TIER_POLICY}" --check-policy
  RESULT_VARIABLE NEX_TEST_TIER_STATUS
  OUTPUT_VARIABLE NEX_TEST_TIER_SUMMARY
  ERROR_VARIABLE NEX_TEST_TIER_ERROR)
if(NOT NEX_TEST_TIER_STATUS EQUAL 0)
  message(FATAL_ERROR "Invalid test-tier policy: ${NEX_TEST_TIER_ERROR}${NEX_TEST_TIER_SUMMARY}")
endif()
file(READ "${NEX_TEST_TIER_POLICY}" NEX_TEST_TIER_JSON)
get_directory_property(NEX_REGISTERED_TESTS TESTS)
foreach(NEX_TIER_TEST IN LISTS NEX_REGISTERED_TESTS)
  string(JSON NEX_TIER_COUNT ERROR_VARIABLE NEX_TIER_ERROR LENGTH
         "${NEX_TEST_TIER_JSON}" tests "${NEX_TIER_TEST}")
  if(NOT NEX_TIER_ERROR STREQUAL "NOTFOUND")
    message(FATAL_ERROR "Classify CTest '${NEX_TIER_TEST}' in cmake/test-tiers.json")
  endif()
  math(EXPR NEX_TIER_LAST "${NEX_TIER_COUNT} - 1")
  set(NEX_TIER_LABELS)
  foreach(NEX_TIER_INDEX RANGE 0 ${NEX_TIER_LAST})
    string(JSON NEX_TIER_LABEL GET "${NEX_TEST_TIER_JSON}" tests
           "${NEX_TIER_TEST}" ${NEX_TIER_INDEX})
    list(APPEND NEX_TIER_LABELS "${NEX_TIER_LABEL}")
  endforeach()
  set_property(TEST "${NEX_TIER_TEST}" APPEND PROPERTY LABELS ${NEX_TIER_LABELS})
endforeach()
