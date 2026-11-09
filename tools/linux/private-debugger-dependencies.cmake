# Standalone LLDB needs LLVMHTTP's imported CURL target before LLVM exports.
find_package(CURL REQUIRED)
find_package(LLVM REQUIRED CONFIG HINTS ${LLVM_DIR} NO_CMAKE_FIND_ROOT_PATH)

# The Bookworm LLVM export names the system development symlink explicitly.
# A private dev prefix supplies the same versioned runtime without installing
# that symlink into /usr. Retain every other exported dependency and check.
if(DEFINED NEX_LLDB_Z3_LIBRARY)
  if(NOT IS_ABSOLUTE "${NEX_LLDB_Z3_LIBRARY}" OR
     NOT EXISTS "${NEX_LLDB_Z3_LIBRARY}")
    message(FATAL_ERROR "NEX_LLDB_Z3_LIBRARY must name an existing absolute library")
  endif()
  get_target_property(original_links LLVMSupport INTERFACE_LINK_LIBRARIES)
  set(private_links)
  foreach(link IN LISTS original_links)
    if(link STREQUAL "/usr/lib/${CMAKE_LIBRARY_ARCHITECTURE}/libz3.so")
      list(APPEND private_links "${NEX_LLDB_Z3_LIBRARY}")
    else()
      list(APPEND private_links "${link}")
    endif()
  endforeach()
  set_property(TARGET LLVMSupport PROPERTY INTERFACE_LINK_LIBRARIES "${private_links}")
endif()
