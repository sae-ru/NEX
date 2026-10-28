cmake_minimum_required(VERSION 3.25)
project(NEXResourceRegions LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Threads REQUIRED)
get_filename_component(NEX_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(NEX_RUNTIME "${NEX_SOURCE}/runtime")
add_executable(resource_regions "${NEX_SOURCE}/tests/resource_regions.cpp"
  "${NEX_RUNTIME}/nex_external_resource.cpp" "${NEX_RUNTIME}/nex_resource_executor.cpp"
  "${NEX_RUNTIME}/nex_resource_region.cpp" "${NEX_RUNTIME}/runtime.cpp"
  "${NEX_RUNTIME}/nex_files.cpp" "${NEX_RUNTIME}/nex_task_external.cpp")
target_include_directories(resource_regions PRIVATE "${NEX_RUNTIME}")
target_compile_definitions(resource_regions PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(resource_regions PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(resource_regions PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
enable_testing()
add_test(NAME logical_resource_regions COMMAND resource_regions)
set_tests_properties(logical_resource_regions PROPERTIES TIMEOUT 90)
add_executable(request_resource_regions "${NEX_SOURCE}/tests/request_resource_regions.cpp"
  "${NEX_RUNTIME}/nex_external_resource.cpp" "${NEX_RUNTIME}/nex_resource_executor.cpp"
  "${NEX_RUNTIME}/nex_resource_region.cpp" "${NEX_RUNTIME}/runtime.cpp"
  "${NEX_RUNTIME}/nex_files.cpp" "${NEX_RUNTIME}/nex_task_external.cpp")
target_include_directories(request_resource_regions PRIVATE "${NEX_RUNTIME}")
target_compile_definitions(request_resource_regions PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(request_resource_regions PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(request_resource_regions PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
add_test(NAME request_resource_regions COMMAND request_resource_regions)
set_tests_properties(request_resource_regions PROPERTIES TIMEOUT 90)
add_executable(native_request_resources "${NEX_SOURCE}/tests/native_request_resources.cpp"
  "${NEX_RUNTIME}/nex_external_resource.cpp" "${NEX_RUNTIME}/nex_resource_executor.cpp"
  "${NEX_RUNTIME}/nex_resource_region.cpp" "${NEX_RUNTIME}/runtime.cpp"
  "${NEX_RUNTIME}/nex_files.cpp" "${NEX_RUNTIME}/nex_task_external.cpp")
target_include_directories(native_request_resources PRIVATE "${NEX_RUNTIME}")
target_compile_definitions(native_request_resources PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(native_request_resources PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(native_request_resources PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
add_test(NAME native_request_resources COMMAND native_request_resources)
set_tests_properties(native_request_resources PROPERTIES TIMEOUT 120)
add_subdirectory("${NEX_SOURCE}/experiments/resource-executor" "${CMAKE_CURRENT_BINARY_DIR}/executor")
add_subdirectory("${NEX_SOURCE}/experiments/external-resources" "${CMAKE_CURRENT_BINARY_DIR}/owned")
