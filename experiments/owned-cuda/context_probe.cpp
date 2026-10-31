// Trusted-host controller test using actual Windows CUDA contexts and memory.
// Language/FFI acceptance is measured separately by the NEX execution corpus.
#include "module.cpp"
#ifndef NEX_CUDA_PROBE_INDEX
#define NEX_CUDA_PROBE_INDEX 0
#endif
static void require(bool value,const char *text){if(!value)throw std::runtime_error(text);}
static CUcontext current(Session &session){
  auto get=reinterpret_cast<decltype(&cuCtxGetCurrent)>(session.driver.symbol("cuCtxGetCurrent"));
  CUcontext context=nullptr;session.driver.check(get(&context),"cuCtxGetCurrent");return context;
}
int main(){try{
  unsigned polls=0;bool rejected=false,rolledBack=false;
  {
    Session a,b;a.start(NEX_CUDA_PROBE_INDEX);b.start(NEX_CUDA_PROBE_INDEX);
    nex_ffi_api_v1 api{};api.poll=[](nex_ffi_call token)->nex_ffi_status{++*reinterpret_cast<unsigned*>(uintptr_t(token));return NEX_FFI_OK;};
    {
      Context outer(a);auto buffer=std::make_unique<Buffer>();buffer->session=&a;buffer->bytes=4;
      a.driver.check(a.driver.p_cuMemAlloc(&buffer->pointer,4),"cuMemAlloc probe");ledger.allocate(4);
      {
        Context inner(b);
        try{Context forbidden(a,&api,nex_ffi_call(uintptr_t(&polls)));}
        catch(const Error &error){rejected=error.code=="E_DEVICE_REENTRANT";}
        require(rejected&&polls==0,"source session reentry was not rejected before host polling");
        buffer.reset();require(ledger.bytes==0,"nested cleanup retained actual device memory");
        require(current(b)==b.context,"nested cleanup did not restore the other CUDA context");
      }
      require(current(a)==a.context,"nested operation did not restore its parent context");
    }
    api.poll=[](nex_ffi_call)->nex_ffi_status{return NEX_FFI_HOST_TRAP;};
    try{Context interrupted(a,&api,0);}catch(const HostStatus &error){rolledBack=error.value==NEX_FFI_HOST_TRAP;}
    require(rolledBack,"constructor host trap was lost");
    {Context restored(a);require(current(a)==a.context,"constructor trap retained TLS or a session lock");}
  }
  require(ledger.bytes==0&&ledger.buffers==ledger.bufferFrees&&ledger.contexts==ledger.contextFrees&&ledger.cleanupErrors==0,"CUDA host probe did not physically settle");
  std::printf("{\"ok\":true,\"actual_CUDA_contexts\":2,\"source_reentry_rejected\":true,\"nested_cleanup_restores_context\":true,\"constructor_trap_rolls_back\":true,\"physical_cleanup_verified\":true}\n");return 0;
}catch(const std::exception &error){std::fprintf(stderr,"CUDA context probe: %s\n",error.what());return 1;}}
