cmake_minimum_required(VERSION 3.25)
project(NEXTaskValueRetirement LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Threads REQUIRED)
get_filename_component(NEX_SOURCE "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(NEX_RUNTIME "${NEX_SOURCE}/runtime")
add_executable(task_value_retirement "${NEX_SOURCE}/tests/task_value_retirement.cpp"
  "${NEX_RUNTIME}/runtime.cpp" "${NEX_RUNTIME}/nex_files.cpp"
  "${NEX_RUNTIME}/nex_external_resource.cpp" "${NEX_RUNTIME}/nex_resource_region.cpp"
  "${NEX_RUNTIME}/nex_resource_executor.cpp" "${NEX_RUNTIME}/nex_task_external.cpp")
target_include_directories(task_value_retirement PRIVATE "${NEX_RUNTIME}")
target_compile_definitions(task_value_retirement PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS)
target_compile_options(task_value_retirement PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(task_value_retirement PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
enable_testing()
add_test(NAME task_value_retirement COMMAND task_value_retirement)
set_tests_properties(task_value_retirement PROPERTIES TIMEOUT 90)
add_executable(task_scheduler_compat "${NEX_SOURCE}/tests/task_scheduler.cpp"
  "${NEX_RUNTIME}/runtime.cpp" "${NEX_RUNTIME}/nex_files.cpp"
  "${NEX_RUNTIME}/nex_resource_region.cpp" "${NEX_RUNTIME}/nex_task_external.cpp")
target_include_directories(task_scheduler_compat PRIVATE "${NEX_RUNTIME}")
target_compile_definitions(task_scheduler_compat PRIVATE NEX_STRUCTURED_WORKERS NEX_ASYNC_TASKS NEX_PROFILE_ENABLED)
target_compile_options(task_scheduler_compat PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(task_scheduler_compat PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
add_test(NAME task_scheduler_compat COMMAND task_scheduler_compat)
set_tests_properties(task_scheduler_compat PROPERTIES TIMEOUT 90)
add_subdirectory("${NEX_SOURCE}/experiments/resource-regions" "${CMAKE_CURRENT_BINARY_DIR}/regions")
