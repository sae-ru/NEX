#pragma once
#include "nex/language.h"
#include "nex_bytes.h"
#include <algorithm>
#include <functional>
#include <sstream>

namespace nex::cuda_detail {
// Canonical fixed-word device values. Only active enum/Result payloads carry
// values; every inactive slot is zero. C++ padding and pointers never cross ABI.
class Values {
  const Program &program;
  struct Layout {Type type;unsigned words;std::string cpp;bool containsContainers;};
  std::map<std::string,Layout> layouts;
  std::set<std::string> building,texts{""};
  std::vector<std::string> order;
  std::map<std::string,unsigned> textIDs;
  size_t textBytes=0;
public:
  bool extended=false,floating=false,conversion=false,hasLists=false,hasBytes=false,utf8Encoding=false,base64Decoding=false;
  const unsigned listCapacity,byteCapacity;
  explicit Values(const Program &p,unsigned capacity=32,unsigned bytes=256):program(p),listCapacity(capacity),byteCapacity(bytes){
    if(!capacity||capacity>1024)throw Error("E_OPTION","CUDA list capacity must be1..1024");
    if(!bytes||bytes>32760)throw Error("E_OPTION","CUDA byte capacity must be1..32760");
  }
  void literal(const std::string &s,Span span){
    extended=true;
    if(s.size()>1023||s.find('\0')!=std::string::npos)throw Error("E_GPU_LIMIT","device text must be NUL-free UTF-8 of at most1023 bytes",span);
    if(texts.insert(s).second){textBytes+=s.size();if(texts.size()>1024||textBytes>65536)throw Error("E_GPU_LIMIT","device text pool exceeds1024 entries or64KiB",span);}
  }
  unsigned ensure(const Type &t,Span span,unsigned depth=0){
    if(depth>32)throw Error("E_GPU_LIMIT","device value nesting exceeds32",span);
    if(t==Type::F64)floating=true;
    if(t==Type::I64||t==Type::F64||t==Type::Bool||t==Type::Unit)return 1;
    if(t==Type::Str){extended=true;return 1;}
    if(t.kind!=Type::Record&&t.kind!=Type::Result&&t.kind!=Type::List&&t!=Type::Bytes)throw Error("E_GPU_TYPE","CUDA value emission does not support "+typeName(t),span);
    extended=true;const auto key=typeName(t);
    if(auto i=layouts.find(key);i!=layouts.end())return i->second.words;
    if(!building.insert(key).second)throw Error("E_GPU_TYPE","recursive device values have no finite layout",span);
    uint64_t n=0;bool containers=t.kind==Type::List||t==Type::Bytes;
    auto child=[&](const Type &f,Span at){auto width=ensure(f,at,depth+1);if(aggregate(f))containers|=layouts.at(typeName(f)).containsContainers;return width;};
    if(t==Type::Bytes){hasBytes=true;n=1+(byteCapacity+7u)/8u;}
    else if(t.kind==Type::List){hasLists=true;n=1+uint64_t(listCapacity)*child(*t.element,span);}
    else if(t.kind==Type::Result)n=1+std::max(2u,child(*t.element,span));
    else{
      const auto &s=program.structure(t.name);
      if(s.opaqueResource||!s.typeParameters.empty())throw Error("E_GPU_TYPE","device values must be concrete and contain no authority",span);
      if(s.enumeration){
        for(const auto &v:s.variants){uint64_t size=0;for(const auto &f:v.fields)size+=child(f.type,f.span);n=std::max(n,size);}++n;
      }else for(const auto &f:s.fields)n+=child(f.type,f.span);
    }
    n=std::max(uint64_t(1),n);if(n>(containers?4096u:64u)||layouts.size()>=128)throw Error("E_GPU_LIMIT","device layout exceeds its64/4096 word bound or128 aggregate types",span);
    building.erase(key);layouts.emplace(key,Layout{t,unsigned(n),"NexValue_"+std::to_string(order.size()),containers});order.push_back(key);return unsigned(n);
  }
  unsigned words(const Type &t)const{return aggregate(t)?layouts.at(typeName(t)).words:1;}
  std::string cpp(const Type &t)const{
    if(aggregate(t))return layouts.at(typeName(t)).cpp;
    switch(t.kind){case Type::I64:return "long long";case Type::F64:return "double";case Type::Bool:return "bool";case Type::Str:return "unsigned int";case Type::Unit:return "NexUnit";default:throw Error("E_GPU_TYPE","unsupported device type");}
  }
  std::string zero(const Type &t)const{return aggregate(t)||t==Type::Unit?"{}":t==Type::Bool?"false":t==Type::F64?"0.0":t==Type::Str?"0U":"0LL";}
  bool aggregate(const Type &t)const{return t.kind==Type::Record||t.kind==Type::Result||t.kind==Type::List||t==Type::Bytes;}
  void finalize(){unsigned i=0;for(const auto &s:texts)textIDs.emplace(s,i++);}
  unsigned id(const std::string &s)const{return textIDs.at(s);}
  size_t idMax()const{return textIDs.size();}
  std::vector<Type> fields(const Type &t,int64_t tag=0)const{
    if(t.kind==Type::Result)return tag==1?std::vector<Type>{*t.element}:std::vector<Type>{Type::Str,Type::Str};
    const auto &s=program.structure(t.name);std::vector<Type> result;
    for(const auto &f:s.enumeration?s.variants.at(size_t(tag)).fields:s.fields)result.push_back(f.type);
    return result;
  }
  unsigned payloadOffset(const Type &t)const{return t.kind==Type::Result||program.structure(t.name).enumeration?1:0;}
  std::string load(const Type &t,const std::string &word)const{
    if(t==Type::Bool)return "("+word+" != 0LL)";
    if(t==Type::F64)return "nex_f_value(nex_unsigned("+word+"), nex_s)";
    if(t==Type::Str)return "static_cast<unsigned int>("+word+")";
    if(t==Type::Unit)return "NexUnit{}";
    return word;
  }
  std::string store(const Type &t,const std::string &value)const{
    if(t==Type::Bool)return "("+value+" ? 1LL : 0LL)";
    if(t==Type::F64)return "nex_bits(nex_f_bits("+value+"))";
    if(t==Type::Str)return "static_cast<long long>("+value+")";
    return t==Type::Unit?"0LL":value;
  }
  std::string normalizer(const Type &t)const{return "nex_decode_"+cpp(t);}
  std::string prelude()const{
    if(!extended)return {};
    std::ostringstream o;o<<"\nstruct NexUnit {};\n";
    // Decode each aggregate with finite bounded loops. Every recursive call is
    // acyclic and topologically earlier; malformed tags never read a payload.
    for(const auto &key:order){const auto &v=layouts.at(key);o<<"struct "<<v.cpp<<" { long long w["<<v.words<<"]; };\n";}
    for(const auto &key:order){const auto &v=layouts.at(key);const auto &t=v.type;
      o<<"__device__ inline "<<v.cpp<<" "<<normalizer(t)<<"("<<v.cpp<<" const &input, NexState &nex_s) {\nif(nex_s.code)return {};\n"<<v.cpp<<" v=input;\n";
      auto payload=[&](const std::vector<Type> &fs,unsigned offset){
        for(const auto &f:fs){const auto ref="v.w["+std::to_string(offset)+"]";
          if(aggregate(f)){
            o<<cpp(f)<<" child_"<<offset<<"{};for(unsigned i=0;i<"<<words(f)<<"U;++i)child_"<<offset<<".w[i]=v.w["<<offset<<"U+i];\n";
            o<<"child_"<<offset<<"="<<normalizer(f)<<"(child_"<<offset<<",nex_s);if(nex_s.code)return {};\nfor(unsigned i=0;i<"<<words(f)<<"U;++i)v.w["<<offset<<"U+i]=child_"<<offset<<".w[i];\n";
          }else{
            if(f==Type::Bool)o<<"if("<<ref<<"!=0LL&&"<<ref<<"!=1LL){nex_s.code=6;return {};}\n";
            if(f==Type::Unit)o<<"if("<<ref<<"!=0LL){nex_s.code=6;return {};}\n";
            if(f==Type::Str)o<<"if(nex_unsigned("<<ref<<")>="<<texts.size()<<"ULL){nex_s.code=6;return {};}\n";
            if(f==Type::F64)o<<ref<<"=nex_bits(nex_f_bits("<<load(f,ref)<<"));if(nex_s.code)return {};\n";
          }
          offset+=words(f);
        }
        if(offset<v.words)o<<"for(unsigned i="<<offset<<"U;i<"<<v.words<<"U;++i)if(v.w[i]!=0LL){nex_s.code=6;return {};}\n";
      };
      if(t==Type::Bytes){
        o<<"if(v.w[0]<0LL||v.w[0]>"<<byteCapacity<<"LL){nex_s.code=6;return {};}\nconst auto length=static_cast<unsigned>(v.w[0]);\nconst auto used=(length+7U)/8U;\nif(length%8U && (nex_unsigned(v.w[used])>>(8U*(length%8U)))){nex_s.code=6;return {};}\nfor(unsigned i=1U+used;i<"<<v.words<<"U;++i)if(v.w[i]!=0LL){nex_s.code=6;return {};}\n";
      }else if(t.kind==Type::List){
        const auto &f=*t.element;const auto width=words(f);const std::string ref="v.w[offset]";
        o<<"if(v.w[0]<0LL||v.w[0]>"<<listCapacity<<"LL){nex_s.code=6;return {};}\nfor(unsigned slot=0;slot<static_cast<unsigned>(v.w[0]);++slot){unsigned offset=1U+slot*"<<width<<"U;\n";
        if(aggregate(f))o<<cpp(f)<<" child{};for(unsigned j=0;j<"<<width<<"U;++j)child.w[j]=v.w[offset+j];\nchild="<<normalizer(f)<<"(child,nex_s);if(nex_s.code)return {};\nfor(unsigned j=0;j<"<<width<<"U;++j)v.w[offset+j]=child.w[j];\n";
        else{
          if(f==Type::Bool)o<<"if("<<ref<<"!=0LL&&"<<ref<<"!=1LL){nex_s.code=6;return {};}\n";
          if(f==Type::Str)o<<"if(nex_unsigned("<<ref<<")>="<<texts.size()<<"ULL){nex_s.code=6;return {};}\n";
          if(f==Type::F64)o<<ref<<"=nex_bits(nex_f_bits("<<load(f,ref)<<"));if(nex_s.code)return {};\n";
        }
        o<<"}\nfor(unsigned i=1U+static_cast<unsigned>(v.w[0])*"<<width<<"U;i<"<<v.words<<"U;++i)if(v.w[i]!=0LL){nex_s.code=6;return {};}\n";
      }else if(t.kind==Type::Result){o<<"if(v.w[0]==1LL){\n";payload(fields(t,1),1);o<<"}else if(v.w[0]==0LL){\n";payload(fields(t,0),1);o<<"}else{nex_s.code=6;return {};}\n";}
      else{const auto &s=program.structure(t.name);if(s.enumeration){o<<"switch(v.w[0]){\n";for(const auto &variant:s.variants){o<<"case "<<variant.ordinal<<"LL:{\n";payload(fields(t,variant.ordinal),1);o<<"break;}\n";}o<<"default:nex_s.code=6;return {};\n}\n";}else payload(fields(t),0);}
      o<<"return v;\n}\n__device__ inline bool nex_equal_"<<v.cpp<<"("<<v.cpp<<" const &a,"<<v.cpp<<" const &b){for(unsigned i=0;i<"<<v.words<<"U;++i)if(a.w[i]!=b.w[i])return false;return true;}\n";
    }
    o<<"__device__ inline long long nex_text_length(unsigned int id,NexState &s){switch(id){\n";
    for(const auto &[s,id]:textIDs){unsigned scalars=0;for(unsigned char c:s)if((c&0xc0)!=0x80)++scalars;o<<"case "<<id<<"U:return "<<scalars<<"LL;\n";}o<<"default:if(!s.code)s.code=6;return 0LL;}}\n";
    if(hasBytes){
      const auto bytes=cpp(Type::Bytes);
      o<<"__device__ inline long long nex_byte_get("<<bytes<<" const &v,unsigned long long index){return static_cast<long long>((nex_unsigned(v.w[1ULL+(index>>3U)])>>((index&7ULL)*8U))&255ULL);}\n";
      o<<"__device__ inline void nex_byte_put("<<bytes<<" &v,unsigned long long index,long long value){const auto slot=1ULL+(index>>3U);const auto shift=static_cast<unsigned>(index&7ULL)*8U;v.w[slot]=nex_bits((nex_unsigned(v.w[slot])&~(255ULL<<shift))|(nex_unsigned(value)<<shift));}\n";
      if(utf8Encoding){
        o<<"__device__ inline "<<bytes<<" nex_utf8_bytes(unsigned int id,NexState &s){"<<bytes<<" r{};switch(id){\n";
        for(const auto &[text,id]:textIDs){o<<"case "<<id<<"U:{\n";if(text.size()>byteCapacity)o<<"if(!s.code)s.code=14;return {};\n";else{o<<"r.w[0]="<<text.size()<<"LL;\n";for(size_t i=0;i<text.size();++i)o<<"nex_byte_put(r,"<<i<<"ULL,"<<unsigned(static_cast<unsigned char>(text[i]))<<"LL);\n";o<<"return r;\n";}o<<"}\n";}
        o<<"default:if(!s.code)s.code=6;return {};}}\n";
      }
      if(base64Decoding){
        const auto result=cpp(Type::result(Type::Bytes));
        o<<"__device__ inline "<<result<<" nex_decode_base64(unsigned int id,NexState &s){"<<result<<" r{};switch(id){\n";
        for(const auto &[text,id]:textIDs){
          o<<"case "<<id<<"U:{\n";
          try{
            const auto decoded=nexrt::ByteBuffer::fromBase64(text).toVector();
            if(decoded.size()>byteCapacity)o<<"if(!s.code)s.code=14;return {};\n";
            else{o<<bytes<<" b{};b.w[0]="<<decoded.size()<<"LL;\n";for(size_t i=0;i<decoded.size();++i)o<<"nex_byte_put(b,"<<i<<"ULL,"<<unsigned(decoded[i])<<"LL);\n";o<<"r.w[0]=1LL;for(unsigned i=0;i<"<<words(Type::Bytes)<<"U;++i)r.w[1U+i]=b.w[i];return r;\n";}
          }catch(const nexrt::DataError &error){if(error.code!="E_BASE64")throw;o<<"r.w[1]="<<this->id("E_BASE64")<<"LL;r.w[2]="<<this->id("invalid canonical base64")<<"LL;return r;\n";}
          o<<"}\n";
        }
        o<<"default:if(!s.code)s.code=6;return {};}}\n";
      }
    }
    if(conversion){const auto t=Type::result(Type::I64);o<<"__device__ inline "<<cpp(t)<<" nex_f_to_integer(double x,NexState &s){\n"<<cpp(t)<<" r{};auto bits=nex_f_bits(x),m=bits&0x7fffffffffffffffULL;unsigned exp=unsigned(m>>52);\nif(exp==2047U){if(!s.code)s.code=7;return r;}\nif(m>0x43e0000000000000ULL||(m==0x43e0000000000000ULL&&!(bits&nex_sign))){r.w[1]="<<id("E_RANGE")<<"LL;r.w[2]="<<id("f64 value is outside i64 range")<<"LL;return r;}\nr.w[0]=1LL;if(exp<1023U)return r;auto significand=(m&0xfffffffffffffULL)|0x10000000000000ULL;unsigned power=exp-1023U;auto magnitude=power>=52U?significand<<(power-52U):significand>>(52U-power);r.w[1]=nex_bits(bits&nex_sign?0ULL-magnitude:magnitude);return r;\n}\n";}
    return o.str();
  }
  llvm::json::Value metadata(const std::vector<Param> &params,const Type &result)const{
    if(!extended)return nullptr;
    llvm::json::Array entries,parameters,pool;
    for(const auto &[s,id]:textIDs){(void)id;pool.push_back(s);}
    for(const auto &param:params)parameters.push_back(int64_t(words(param.type)));
    std::set<std::string> emitted;
    std::function<void(const Type&)> add=[&](const Type &t){
      const auto name=typeName(t);if(!emitted.insert(name).second)return;
      llvm::json::Object entry{{"type",name},{"words",int64_t(words(t))}};
      if(t==Type::Bytes){entry["kind"]="bytes";entry["capacity"]=int64_t(byteCapacity);entry["length_offset"]=0;entry["elements_offset"]=1;entry["octets_per_word"]=8;entry["octet_order"]="least_significant_first";}
      else if(t.kind==Type::List){add(*t.element);entry["kind"]="list";entry["element_type"]=typeName(*t.element);entry["element_words"]=int64_t(words(*t.element));entry["capacity"]=int64_t(listCapacity);entry["length_offset"]=0;entry["elements_offset"]=1;}
      else if(t.kind==Type::Result){add(*t.element);add(Type::Str);entry["kind"]="result";entry["ok_tag"]=1;entry["error_tag"]=0;entry["payload_type"]=typeName(*t.element);entry["payload_offset"]=1;entry["code_offset"]=1;entry["message_offset"]=2;}
      else if(t.kind==Type::Record){const auto &s=program.structure(t.name);entry["kind"]=s.enumeration?"enum":"record";
        auto fs=[&](const std::vector<Param> &members,unsigned offset){llvm::json::Array a;for(const auto &f:members){add(f.type);a.push_back(llvm::json::Object{{"name",f.name},{"type",typeName(f.type)},{"offset",int64_t(offset)}});offset+=words(f.type);}return a;};
        if(s.enumeration){llvm::json::Array variants;for(const auto &v:s.variants)variants.push_back(llvm::json::Object{{"name",v.name},{"tag",v.ordinal},{"fields",fs(v.fields,1)}});entry["variants"]=std::move(variants);}else entry["fields"]=fs(s.fields,0);
      }else entry["kind"]=t==Type::Str?"text_id":"scalar";
      entries.push_back(std::move(entry));
    };
    for(const auto &p:params)add(p.type);add(result);
    // Include internal types too: the strings/Result diagnostic IDs are part
    // of the exact emission even when the root's signature is scalar.
    for(const auto &key:order)add(layouts.at(key).type);
    llvm::json::Object metadata{{"schema",hasBytes?"nex.cuda-values/3":hasLists?"nex.cuda-values/2":"nex.cuda-values/1"},{"word_bytes",8},{"byte_order","little"},{"maximum_words",hasLists||hasBytes?4096:64},{"maximum_depth",32},{"parameter_words",std::move(parameters)},{"result_words",int64_t(words(result))},{"types",std::move(entries)},{"text_pool",std::move(pool)},{"inactive_words_zero",true},{"result_failure_status_mask",int64_t(0x80000000ULL)},{"result_code_shift",10},{"result_text_id_bits",10}};
    if(hasLists){metadata["list_capacity"]=int64_t(listCapacity);metadata["list_bounds_status"]=9;metadata["list_capacity_status"]=10;if(!hasBytes)metadata["maximum_words_without_lists"]=64;}
    if(hasBytes){metadata["byte_capacity"]=int64_t(byteCapacity);metadata["byte_index_status"]=11;metadata["byte_slice_status"]=12;metadata["byte_range_status"]=13;metadata["byte_capacity_status"]=14;metadata["maximum_words_without_containers"]=64;}
    return metadata;
  }
};
}
