// CPU-only C API ownership/dispatch fixture. It never initializes a GPU and is
// not a fallback or a production provider. Reuse the actual outcome publisher.
#define nex_ffi_module_entry nex_fixture_unused_production_entry
#include "module.cpp"
#undef nex_ffi_module_entry
#include <utility>
namespace host_fixture {
std::atomic<unsigned> next{1};std::mutex logMutex;
void event(const char *name,unsigned id,unsigned kind){std::lock_guard lock(logMutex);if(auto path=std::getenv("NEX_CUDA_OUTCOME_EVENTS")){std::ofstream out(path,std::ios::app);out<<JSON{{"event",name},{"id",id},{"kind",kind},{"actual_GPU",false}}.dump()<<'\n';}}
struct Object{unsigned id=next++,kind,mode=0,special=0;Object *parent=nullptr;std::vector<uint8_t> data;size_t offset=0;explicit Object(unsigned kind):kind(kind){}};
struct Input:Creation{Object *parent=nullptr;unsigned mode=0;explicit Input(Kind kind):Creation(kind){}};
void destroy(void *p)noexcept{auto value=static_cast<Object*>(p);event("destroy",value->id,value->kind);delete value;}
std::pair<std::string,std::string> packet(unsigned mode){
 if(mode==2)return {std::string("source\0code",11),std::string("before\0after",12)+"🌍"};
 if(mode==3){std::string code,message;for(unsigned i=0;i<50;++i)code+="源";for(unsigned i=0;i<500;++i)message+="msg🌍";return {code,message};}
 return {"CUSTOM", "runtime message: 🌍"};
}
nex_ffi_status create(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out)noexcept{
 auto &in=*static_cast<Input*>(static_cast<Creation*>(user));
 try{checked(api->poll(call));auto kind=in.kind==Creation::SessionOpen?0u:in.kind==Creation::ReaderOpen?2u:1u;auto value=new Object(kind);value->parent=in.parent;value->data=in.data;*out=value;event("create",value->id,value->kind);
  if(in.kind==Creation::BufferGenerated){event("settled",value->id,value->kind);if(in.mode==1||in.mode==2||in.mode==3||in.mode==6){auto p=packet(in.mode);in.sourceCode=std::move(p.first);in.sourceMessage=std::move(p.second);in.sourceFault=true;return NEX_FFI_INTERNAL;}}
  return NEX_FFI_OK;
 }catch(const HostStatus&e){return e.value;}catch(...){return NEX_FFI_INTERNAL;}
}
nex_ffi_status make(const nex_ffi_api_v1 *api,nex_ffi_call call,Input &in,nex_ffi_ref parent,nex_ffi_ref *out){auto r=constructResourceResult(api,call,in,sizeof(Object)+in.data.size(),parent,out,create,destroy);if(in.sourceFault&&r==NEX_FFI_OK)event("fault_published",0,0);return r;}
Object *get(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref ref,unsigned argument){return static_cast<Object*>(borrow(api,call,ref,argument));}
nex_ffi_status invoke(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
 try{checked(api->poll(call));auto op=uintptr_t(user);
  if(op==9){event("host_fatal",0,0);return callback(api,call,args,count,out,user);}
  if(op==10||op==11)return callback(api,call,args,count,out,user);
  if(op==1){Input in{Creation::SessionOpen};return make(api,call,in,0,out);}
  if(op==2){Input in{Creation::BufferUpload};in.parent=get(api,call,args[0],0);uint64_t n=0,written=0;checked(api->byte_size(call,args[2],&n));if(n>262144)return NEX_FFI_LIMIT;in.data.resize(n);checked(api->copy_bytes(call,args[2],0,in.data.data(),n,&written));if(written!=n)return NEX_FFI_INTERNAL;if(!in.data.empty()&&in.data[0]==8)return failure(api,call,out,"E_GPU_INPUT","controlled upload failure");return make(api,call,in,args[0],out);}
  if(op==3){auto session=get(api,call,args[0],0);uint64_t n=0;checked(api->child_count(call,args[1],&n));if(n!=GENERATED_ARGUMENTS)return NEX_FFI_ARGUMENT;nex_ffi_type list=0,type=0;checked(api->argument_type(call,1,&list));checked(api->type_child(call,list,0,0,&type));ValueReference first(api,call);checked(api->child(call,args[1],0,&first.value));void *raw=nullptr;checked(api->resource_borrow(call,first.value,type,&raw));auto input=static_cast<Object*>(raw);auto mode=input->data.empty()?0u:unsigned(input->data[0]);if(mode==4)return failure(api,call,out,"E_GPU_INPUT","controlled host failure");if(mode==6&&session->special++==0)mode=0;
   Input in{Creation::BufferGenerated};in.parent=session;in.mode=mode;auto lanes=integer(api,call,args[2]);if(lanes<1||lanes>32768)return NEX_FFI_RANGE;in.data.resize(size_t(lanes)*8);for(size_t i=0;i<in.data.size();i+=8){in.data[i+6]=69;in.data[i+7]=64;}return make(api,call,in,args[0],out);}
  if(op==4){Input in{Creation::ReaderOpen};in.parent=get(api,call,args[0],0);return make(api,call,in,args[0],out);}
  if(op==8){auto cursor=get(api,call,args[0],0);auto &data=cursor->parent->data;auto n=std::min<size_t>(262144,data.size()-cursor->offset);ValueReference value(api,call);checked(api->make_bytes(call,data.data()+cursor->offset,n,&value.value));cursor->offset+=n;return api->make_success(call,value.value,out);}
  if(op==5){const std::string label="explicit CPU outcome ownership fixture";return api->make_string(call,reinterpret_cast<const uint8_t*>(label.data()),label.size(),out);}
  if(op==6||op==7)return api->make_i64(call,0,out);
  return NEX_FFI_ARGUMENT;
 }catch(const HostStatus&e){return e.value;}catch(...){return NEX_FFI_INTERNAL;}
}
#define ROW(name,id) {sizeof(nex_ffi_export_v1),0,#name,PIN_##name,invoke,(void*)id}
const nex_ffi_export_v1 entries[]={
 {sizeof(nex_ffi_export_v1),0,"open",PIN_OPEN,invoke,(void*)1},
 {sizeof(nex_ffi_export_v1),0,"upload",PIN_UPLOAD,invoke,(void*)2},
 {sizeof(nex_ffi_export_v1),0,"map",PIN_MAP,invoke,(void*)3},
 {sizeof(nex_ffi_export_v1),0,"download",PIN_DOWNLOAD,invoke,(void*)4},
 {sizeof(nex_ffi_export_v1),0,"name",PIN_NAME,invoke,(void*)5},
 {sizeof(nex_ffi_export_v1),0,"kernel_ns",PIN_KERNEL_NS,invoke,(void*)6},
 {sizeof(nex_ffi_export_v1),0,"busy",PIN_BUSY,invoke,(void*)7},
 {sizeof(nex_ffi_export_v1),0,"read_next",PIN_READ_NEXT,invoke,(void*)8},
 {sizeof(nex_ffi_export_v1),0,"fatal",PIN_FATAL,invoke,(void*)9},
 {sizeof(nex_ffi_export_v1),0,"encode_f64",PIN_ENCODE_F64,invoke,(void*)10},
 {sizeof(nex_ffi_export_v1),0,"decode_f64",PIN_DECODE_F64,invoke,(void*)11}
};
}
#ifdef _WIN32
#define EXPORTED __declspec(dllexport)
#else
#define EXPORTED __attribute__((visibility("default")))
#endif
extern "C" EXPORTED const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){static const nex_ffi_module_v1 module{1,sizeof(nex_ffi_module_v1),11,sizeof(nex_ffi_export_v1),host_fixture::entries};return abi==1&&size>=NEX_FFI_V1_TRAP_SIZE?&module:nullptr;}
