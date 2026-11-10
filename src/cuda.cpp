#include "nex/cuda.h"
#include "cuda_floating_runtime.h"
#include "cuda_values.h"
#include <algorithm>
#include <iomanip>
#include <sstream>
#include <string_view>

namespace nex {
namespace {
constexpr std::string_view runtime=R"nexcuda(
// CUDA C++20. Signed i64 is long long on both Windows and Linux.
static_assert(sizeof(long long)==8 && sizeof(unsigned long long)==8);
struct NexState { unsigned int code; unsigned int remaining; };
static constexpr unsigned long long nex_sign=0x8000000000000000ULL;
static constexpr unsigned long long nex_max=0x7fffffffffffffffULL;
__device__ inline long long nex_bits(unsigned long long x) {
  // C++20 integral conversion is the unique congruent destination value.
  return static_cast<long long>(x);
}
__device__ inline unsigned long long nex_unsigned(long long x) {
  return static_cast<unsigned long long>(x);
}
__device__ inline bool nex_tick(NexState &s) {
  if(s.code)return false;
  if(!s.remaining){s.code=4;return false;}
  --s.remaining;return true;
}
__device__ inline long long nex_add(long long a,long long b,NexState &s) {
  unsigned long long x=nex_unsigned(a),y=nex_unsigned(b),z=x+y;
  if(((x^z)&(y^z)&nex_sign)!=0){s.code=1;return 0;}
  return nex_bits(z);
}
__device__ inline long long nex_sub(long long a,long long b,NexState &s) {
  unsigned long long x=nex_unsigned(a),y=nex_unsigned(b),z=x-y;
  if(((x^y)&(x^z)&nex_sign)!=0){s.code=1;return 0;}
  return nex_bits(z);
}
__device__ inline long long nex_neg(long long a,NexState &s) {
  unsigned long long x=nex_unsigned(a);
  if(x==nex_sign){s.code=1;return 0;}
  return nex_bits(0ULL-x);
}
__device__ inline unsigned long long nex_magnitude(long long x) {
  unsigned long long bits=nex_unsigned(x);return x<0?0ULL-bits:bits;
}
__device__ inline long long nex_mul(long long a,long long b,NexState &s) {
  bool negative=(a<0)!=(b<0);
  unsigned long long x=nex_magnitude(a),y=nex_magnitude(b),limit=negative?nex_sign:nex_max;
  if(x && y>limit/x){s.code=1;return 0;}
  unsigned long long product=x*y;return nex_bits(negative?0ULL-product:product);
}
__device__ inline long long nex_div(long long a,long long b,NexState &s) {
  if(!b){s.code=2;return 0;}
  if(nex_unsigned(a)==nex_sign && b==-1LL){s.code=1;return 0;}
  unsigned long long value=nex_magnitude(a)/nex_magnitude(b);
  return nex_bits((a<0)!=(b<0)?0ULL-value:value);
}
__device__ inline long long nex_mod(long long a,long long b,NexState &s) {
  if(!b){s.code=2;return 0;}
  unsigned long long value=nex_magnitude(a)%nex_magnitude(b);
  return nex_bits(a<0?0ULL-value:value);
}
)nexcuda";
constexpr size_t maximumSourceBytes=16*1024*1024;

std::string scalar(const Type &type,Span span){
  switch(type.kind){
    case Type::I64:return "long long";
    case Type::F64:return "double";
    case Type::Bool:return "bool";
    case Type::Unit:return "void";
    default:throw Error("E_GPU_TYPE","CUDA scalar emission does not support "+typeName(type),span);
  }
}

class Emitter {
  const Program &program;
  const Function &root;
  cuda_detail::Values values;
  size_t valuePrefixBytes=0;
  std::string layout,text;
  std::map<std::string,const Function*> functions;
  std::map<std::string,std::string> names;
  std::set<std::string> visiting,visited;
  std::vector<const Function*> order;
  unsigned indentation=0,serial=0,lines=0;
  Type result=Type::Unit;
  Span where;
  bool floatingPoint=false;
  using Scope=std::map<std::string,std::string>;

  void checkType(const Type &type,Span span){values.ensure(type,span);floatingPoint=values.floating;}
  std::string deviceType(const Type &type,Span span)const{return values.aggregate(type)||type==Type::Str||type==Type::Unit?values.cpp(type):scalar(type,span);}
  void validatePattern(const P &pattern){
    if(!pattern)throw Error("E_GPU_UNSUPPORTED","missing checked CUDA pattern");
    checkType(pattern->type,pattern->span);
    if(pattern->kind==Pattern::String)values.literal(pattern->text,pattern->span);
    else if(pattern->kind!=Pattern::Binding&&pattern->kind!=Pattern::Wildcard&&pattern->kind!=Pattern::Integer&&pattern->kind!=Pattern::Boolean&&pattern->kind!=Pattern::Constructor&&pattern->kind!=Pattern::List)
      throw Error("E_GPU_UNSUPPORTED","unsupported CUDA value pattern",pattern->span);
    if(pattern->kind==Pattern::List&&pattern->args.size()>values.listCapacity)throw Error("E_GPU_LIMIT","device list pattern exceeds declared capacity",pattern->span);
    for(const auto &child:pattern->args)validatePattern(child);
  }

  void discover(const Function &function,Span caller){
    if(visiting.contains(function.name))throw Error("E_GPU_RECURSION","recursive CUDA call graph: "+function.name,caller);
    if(visited.contains(function.name))return;
    if(visiting.size()>=128)throw Error("E_GPU_LIMIT","CUDA call depth exceeds128 functions",caller);
    if(function.realm!="shared"||!function.effects.empty())
      throw Error("E_GPU_REALM","CUDA functions must be shared and pure: "+function.name,function.span);
    if(function.foreign||function.closure||!function.captures.empty()||!function.typeParameters.empty())
      throw Error("E_GPU_UNSUPPORTED","CUDA functions must be concrete, without captures or foreign authority",function.span);
    checkType(function.result,function.span);
    for(const auto &parameter:function.params){
      if(parameter.type==Type::Unit)values.extended=true;
      checkType(parameter.type,parameter.span);
    }
    visiting.insert(function.name);
    validateBlock(function.body);
    visiting.erase(function.name);visited.insert(function.name);order.push_back(&function);
    if(order.size()>128)throw Error("E_GPU_LIMIT","CUDA call graph exceeds128 functions",function.span);
  }

  void validateExpression(const E &expression){
    if(!expression)return;
    checkType(expression->type,expression->span);
    switch(expression->kind){
      case Expr::Integer:case Expr::Floating:case Expr::Boolean:case Expr::Name:break;
      case Expr::String:values.literal(expression->text,expression->span);break;
      case Expr::Field:case Expr::Propagate:break;
      case Expr::List:
        if(expression->args.size()>values.listCapacity)throw Error("E_GPU_LIMIT","device list literal exceeds declared capacity",expression->span);
        break;
      case Expr::Index:
        if(expression->args[0]->type.kind!=Type::List&&expression->args[0]->type!=Type::Bytes&&!(expression->args[0]->type==Type::Str&&values.textCapacity))throw Error("E_GPU_UNSUPPORTED","CUDA text indexing requires --text-capacity",expression->span);
        break;
      case Expr::Unary:
        if(expression->args.size()!=1||(expression->text!="-"&&expression->text!="!"))
          throw Error("E_GPU_UNSUPPORTED","unsupported CUDA unary expression",expression->span);
        break;
      case Expr::Binary:{
        static const std::set<std::string> operators={"+","-","*","/","%","==","!=","<","<=",">",">=","&&","||"};
        if(expression->args.size()!=2||!operators.contains(expression->text))
          throw Error("E_GPU_UNSUPPORTED","unsupported CUDA binary expression",expression->span);
        if(expression->args[0]->type.heap()&&expression->text!="=="&&expression->text!="!="&&!(expression->text=="+"&&(expression->type.kind==Type::List||expression->type==Type::Bytes||(expression->type==Type::Str&&values.textCapacity))))
          throw Error("E_GPU_UNSUPPORTED","device values support equality; dynamic heap/text arithmetic is unavailable",expression->span);
        break;
      }
      case Expr::Call:
        if(expression->text=="as_i64"){
          values.conversion=true;values.literal("E_RANGE",expression->span);values.literal("f64 value is outside i64 range",expression->span);
        }else if(expression->text=="bytes"){
          values.literal("E_RANGE",expression->span);values.literal("byte value must be between 0 and 255",expression->span);
        }else if(expression->text=="utf8_bytes")values.utf8Encoding=true;
        else if(expression->text=="decode_base64"){
          values.base64Decoding=true;values.literal("E_BASE64",expression->span);values.literal("invalid canonical base64",expression->span);
        }
        else if(expression->text=="decode_utf8"||expression->text=="encode_base64"||expression->text=="str"){
          if(!values.textCapacity)throw Error("E_GPU_UNSUPPORTED","dynamic CUDA text requires --text-capacity",expression->span);
          if(expression->text=="decode_utf8"){values.literal("E_UTF8",expression->span);values.literal("invalid UTF-8 string",expression->span);values.literal("invalid Unicode scalar",expression->span);}
          if(expression->text=="str"&&expression->args[0]->type!=Type::I64&&expression->args[0]->type!=Type::Bool)throw Error("E_GPU_UNSUPPORTED","CUDA str currently formats i64 and bool",expression->span);
        }
        else if(expression->text=="slice"){
          if(expression->args[0]->type!=Type::Bytes&&!(expression->args[0]->type==Type::Str&&values.textCapacity))throw Error("E_GPU_UNSUPPORTED","CUDA text slicing requires --text-capacity",expression->span);
        }else if(expression->text=="ok"||expression->text=="err"||expression->text=="is_ok"||expression->text=="unwrap"||expression->text=="error_code"||expression->text=="error_message"||expression->text=="len"||expression->text=="push"||expression->text=="set"||program.hasStructure(expression->text)||program.variant(expression->text)){
          if(expression->text=="len"&&expression->args[0]->type!=Type::Str&&expression->args[0]->type.kind!=Type::List&&expression->args[0]->type!=Type::Bytes)throw Error("E_GPU_TYPE","device len requires bounded text, a list or bytes",expression->span);
        }else if(expression->text=="as_f64"){
          if(expression->args.size()!=1||expression->args[0]->type!=Type::I64||expression->type!=Type::F64)
            throw Error("E_GPU_TYPE","invalid checked CUDA integer-to-f64 conversion",expression->span);
        }else if(expression->text!="assert"){
          auto found=functions.find(expression->text);
          if(found==functions.end())throw Error("E_GPU_UNSUPPORTED","unsupported CUDA builtin or callee: "+expression->text,expression->span);
          discover(*found->second,expression->span);
        }else if(expression->args.size()!=1||expression->type!=Type::Unit)
          throw Error("E_GPU_UNSUPPORTED","unsupported CUDA assertion",expression->span);
        break;
      case Expr::Match:
        if(expression->args.empty()||expression->arms.empty())
          throw Error("E_GPU_UNSUPPORTED","missing checked CUDA match arms",expression->span);
        for(const auto &arm:expression->arms){
          validatePattern(arm->pattern);
          if((arm->guard&&arm->guard>=expression->args.size())||
             (!expression->statementMatch&&(!arm->value||arm->value>=expression->args.size())))
            throw Error("E_GPU_UNSUPPORTED","invalid checked CUDA match operand",arm->span);
          validateBlock(arm->body);
        }
        break;
      default:throw Error("E_GPU_UNSUPPORTED","unsupported CUDA expression",expression->span);
    }
    for(const auto &argument:expression->args)validateExpression(argument);
  }

  void validateBlock(const std::vector<S> &statements){
    for(const auto &statement:statements){
      switch(statement->kind){
        case Stmt::Let:case Stmt::Var:
          if(statement->type==Type::Unit)values.extended=true;
          checkType(statement->type,statement->span);break;
        case Stmt::Assign:case Stmt::Expression:case Stmt::Return:case Stmt::If:case Stmt::While:case Stmt::Match:break;
        default:throw Error("E_GPU_UNSUPPORTED","unsupported CUDA statement",statement->span);
      }
      validateExpression(statement->expr);
      validateBlock(statement->body);validateBlock(statement->alternative);
    }
  }

  void line(const std::string &value){
    const size_t extra=2*indentation+value.size()+1;
    if(extra>maximumSourceBytes-text.size()-runtime.size()-(floatingPoint?cuda_detail::floatingRuntime.size():0)-valuePrefixBytes-1)
      throw Error("E_GPU_LIMIT","generated CUDA source exceeds16MiB",where);
    text.append(2*indentation,' ');text+=value;text+='\n';++lines;
  }
  std::string temporary(){return "nex_v_"+std::to_string(++serial);}
  std::string zero(const Type &type)const{return values.zero(type);}
  std::string stop()const{return result==Type::Unit?"return;":"return "+zero(result)+";";}
  void guard(){line("if (nex_s.code) { "+stop()+" }");}
  void tick(){line("if (!nex_tick(nex_s)) { "+stop()+" }");}

  std::string patternCondition(const P &pattern,const std::string &subject){
    switch(pattern->kind){
      case Pattern::Binding:case Pattern::Wildcard:return "true";
      case Pattern::String:return values.hasText?"nex_equal_"+values.cpp(Type::Str)+"("+subject+", "+values.textLiteral(pattern->text)+")":subject+" == "+values.textLiteral(pattern->text);
      case Pattern::Boolean:return subject+" == "+(pattern->number?"true":"false");
      case Pattern::Integer:{
        std::ostringstream bits;bits<<std::hex<<std::setfill('0')<<std::setw(16)<<static_cast<uint64_t>(pattern->number);
        return subject+" == nex_bits(0x"+bits.str()+"ULL)";
      }
      default:throw Error("E_GPU_UNSUPPORTED","unsupported CUDA scalar pattern",pattern->span);
    }
  }

  std::string extract(const Type &type,const std::string &base,const std::string &offset){
    if(!values.aggregate(type))return values.load(type,base+".w["+offset+"]");
    const auto name=temporary();line(deviceType(type,where)+" "+name+"{};");
    line("for(unsigned i=0;i<"+std::to_string(values.words(type))+"U;++i) "+name+".w[i] = "+base+".w[("+offset+")+i];");return name;
  }
  std::string extract(const Type &type,const std::string &base,unsigned offset){return extract(type,base,std::to_string(offset)+"U");}
  void insert(const Type &type,const std::string &value,const std::string &base,const std::string &offset){
    if(values.aggregate(type))line("for(unsigned i=0;i<"+std::to_string(values.words(type))+"U;++i) "+base+".w[("+offset+")+i] = "+value+".w[i];");
    else line(base+".w["+offset+"] = "+values.store(type,value)+";");
  }
  void insert(const Type &type,const std::string &value,const std::string &base,unsigned offset){insert(type,value,base,std::to_string(offset)+"U");}
  std::string listOffset(const Type &list,const std::string &index)const{return "1ULL+static_cast<unsigned long long>("+index+")*"+std::to_string(values.words(*list.element))+"ULL";}
  void listBounds(const std::string &list,const std::string &index){line("if ("+index+" < 0LL || "+index+" >= "+list+".w[0]) { nex_s.code = 9; "+stop()+" }");}
  void listLimit(const std::string &length){line("if ("+length+" > "+std::to_string(values.listCapacity)+"LL) { nex_s.code = 10; "+stop()+" }");}
  void byteBounds(const std::string &bytes,const std::string &index){line("if ("+index+" < 0LL || "+index+" >= "+bytes+".w[0]) { nex_s.code = 11; "+stop()+" }");}
  void byteRange(const std::string &value){line("if ("+value+" < 0LL || "+value+" > 255LL) { nex_s.code = 13; "+stop()+" }");}
  void byteLimit(const std::string &length){line("if ("+length+" > "+std::to_string(values.byteCapacity)+"LL) { nex_s.code = 14; "+stop()+" }");}
  void textLimit(const std::string &length){line("if ("+length+" > "+std::to_string(values.textCapacity)+"LL) { nex_s.code = 18; "+stop()+" }");}
  std::string byteConstruction(const Type &type,const std::string &input){
    // Validate source octets before the additional device-capacity bound, so a
    // recoverable E_RANGE remains recoverable even for an oversized input.
    const auto valid=temporary();line("bool "+valid+" = true;");
    line("for(unsigned i=0;i<static_cast<unsigned>("+input+".w[0]);++i) if("+input+".w[1U+i]<0LL||"+input+".w[1U+i]>255LL){"+valid+"=false;break;}");
    const auto result=temporary();line(deviceType(type,where)+" "+result+"{};");line("if (!"+valid+") {");++indentation;
    const auto error=construct(type,{values.textLiteral("E_RANGE"),values.textLiteral("byte value must be between 0 and 255")},0);line(result+" = "+error+";");--indentation;line("} else {");++indentation;
    byteLimit(input+".w[0]");const auto bytes=temporary();line(deviceType(Type::Bytes,where)+" "+bytes+"{};");line(bytes+".w[0] = "+input+".w[0];");line("for(unsigned i=0;i<static_cast<unsigned>("+input+".w[0]);++i) nex_byte_put("+bytes+",i,"+input+".w[1U+i]);");
    const auto success=construct(type,{bytes},1);line(result+" = "+success+";");--indentation;line("}");return result;
  }
  std::string decodeText(const Type &type,const std::string &input,bool utf8){
    auto issue=temporary(),count=temporary(),name=temporary();
    if(utf8)line("unsigned "+issue+" = nex_utf8_error("+input+");");
    else{line("unsigned "+count+" = 0;");line("bool "+issue+" = !nex_base64_size("+input+", "+count+");");}
    line(deviceType(type,where)+" "+name+"{};");line("if ("+issue+") {");++indentation;
    const auto message=utf8?"("+issue+" == 1U ? "+values.textLiteral("invalid UTF-8 string")+" : "+values.textLiteral("invalid Unicode scalar")+")":values.textLiteral("invalid canonical base64");
    auto error=construct(type,{values.textLiteral(utf8?"E_UTF8":"E_BASE64"),message},0);line(name+" = "+error+";");--indentation;line("} else {");++indentation;
    if(utf8)textLimit(input+".w[0]");else byteLimit(count);
    auto payload=temporary();const auto &payloadType=*type.element;
    line(deviceType(payloadType,where)+" "+payload+" = "+(utf8?"nex_octet_slice<"+values.cpp(Type::Str)+">("+input+", 0U, static_cast<unsigned>("+input+".w[0]))":"nex_base64_decode<"+values.cpp(Type::Bytes)+">("+input+", "+count+")")+";");
    auto success=construct(type,{payload},1);line(name+" = "+success+";");--indentation;line("}");return name;
  }
  std::string construct(const Type &type,const std::vector<std::string> &arguments,int64_t tag=0){
    const auto name=temporary();line(deviceType(type,where)+" "+name+"{};");
    unsigned offset=values.payloadOffset(type);if(offset)line(name+".w[0] = "+std::to_string(tag)+"LL;");
    const auto fs=values.fields(type,tag);for(size_t i=0;i<fs.size();++i){insert(fs[i],arguments.at(i),name,offset);offset+=values.words(fs[i]);}return name;
  }
  void pattern(const P &p,const std::string &subject,const std::string &accepted,Scope &bound){
    line("if ("+accepted+") {");++indentation;
    if(p->kind==Pattern::Binding)line(bound.at(p->text)+" = "+subject+";");
    else if(p->kind==Pattern::List){
      line(accepted+" = ("+subject+".w[0] == "+std::to_string(p->args.size())+"LL);");
      for(size_t i=0;i<p->args.size();++i){line("if ("+accepted+") {");++indentation;auto child=extract(*p->type.element,subject,1+unsigned(i)*values.words(*p->type.element));pattern(p->args[i],child,accepted,bound);--indentation;line("}");}
    }else if(p->kind==Pattern::Constructor){
      auto offset=values.payloadOffset(p->type);
      if(offset)line(accepted+" = ("+subject+".w[0] == "+std::to_string(p->ordinal)+"LL);");
      const auto fs=values.fields(p->type,p->ordinal);
      // Tag and preceding patterns guard every payload read, including nested
      // f64 fields. Inactive alternatives are never evaluated.
      for(size_t i=0;i<p->args.size();++i){line("if ("+accepted+") {");++indentation;auto child=extract(fs[i],subject,offset);pattern(p->args[i],child,accepted,bound);--indentation;line("}");offset+=values.words(fs[i]);}
    }else if(p->kind!=Pattern::Wildcard)line(accepted+" = ("+patternCondition(p,subject)+");");
    --indentation;line("}");
  }

  std::string matching(const E &value,const Scope &scope){
    // Keep one immutable subject across failed patterns and guards. Bindings
    // point to that already evaluated scalar, never to a caller's mutable slot.
    const auto subject=expression(value->args.at(0),scope);
    const auto matched=temporary();std::string output;
    if(!value->statementMatch&&value->type!=Type::Unit){
      output=temporary();line(deviceType(value->type,value->span)+" "+output+" = "+zero(value->type)+";");
    }
    line("bool "+matched+" = false;");
    for(const auto &arm:value->arms){
      line("if (!"+matched+") {");++indentation;
      where=arm->span;tick(); // Each attempted arm consumes the lane budget.
      Scope bound=scope;
      if(values.extended){
        visitPattern(arm->pattern,[&](const P &p){if(p->kind==Pattern::Binding){auto name=temporary();line(deviceType(p->type,p->span)+" "+name+"{};");bound[p->text]=name;}});
        auto accepted=temporary();line("bool "+accepted+" = true;");pattern(arm->pattern,subject,accepted,bound);line("if ("+accepted+") {");}
      else line("if ("+patternCondition(arm->pattern,subject)+") {");
      ++indentation;
      if(!values.extended&&arm->pattern->kind==Pattern::Binding)bound[arm->pattern->text]=subject;
      if(arm->guard){
        const auto condition=expression(value->args.at(arm->guard),bound);
        line("if ("+condition+") {");++indentation;
      }
      line(matched+" = true;");
      if(value->statementMatch)block(arm->body,bound);
      else{
        const auto accepted=expression(value->args.at(arm->value),bound);
        if(value->type!=Type::Unit)line(output+" = "+accepted+";");
      }
      if(arm->guard){--indentation;line("}");}
      --indentation;line("}");--indentation;line("}");
    }
    line("if (!"+matched+") { nex_s.code = 5; "+stop()+" }");
    return output;
  }

  std::string expression(const E &value,const Scope &scope){
    if(!value)throw Error("E_GPU_UNSUPPORTED","missing CUDA expression",where);
    where=value->span;tick();std::string generated;
    switch(value->kind){
      case Expr::Integer:{
        std::ostringstream bits;bits<<std::hex<<std::setfill('0')<<std::setw(16)<<static_cast<uint64_t>(value->number);
        generated="nex_bits(0x"+bits.str()+"ULL)";break;
      }
      case Expr::Floating:{
        std::ostringstream bits;bits<<std::hex<<std::setfill('0')<<std::setw(16)<<static_cast<uint64_t>(value->number);
        generated="nex_f_value(0x"+bits.str()+"ULL, nex_s)";break;
      }
      case Expr::Boolean:generated=value->number?"true":"false";break;
      case Expr::String:generated=values.textLiteral(value->text);break;
      case Expr::List:{
        const auto name=temporary();line(deviceType(value->type,where)+" "+name+"{};");line(name+".w[0] = "+std::to_string(value->args.size())+"LL;");
        for(size_t i=0;i<value->args.size();++i){auto item=expression(value->args[i],scope);insert(*value->type.element,item,name,1+unsigned(i)*values.words(*value->type.element));}return name;
      }
      case Expr::Index:{
        auto base=expression(value->args[0],scope),index=expression(value->args[1],scope);
        if(value->args[0]->type==Type::Str){
          line("if ("+index+" < 0LL || "+index+" >= nex_unicode_length("+base+")) { nex_s.code = 16; "+stop()+" }");auto offset=temporary(),end=temporary();line("unsigned "+offset+" = nex_unicode_offset("+base+", static_cast<unsigned>("+index+"));");line("unsigned "+end+" = nex_unicode_offset("+base+", static_cast<unsigned>("+index+")+1U);");generated="nex_octet_slice<"+values.cpp(Type::Str)+">("+base+", "+offset+", "+end+"-"+offset+")";
        }else if(value->args[0]->type==Type::Bytes){byteBounds(base,index);generated="nex_byte_get("+base+",static_cast<unsigned long long>("+index+"))";}
        else{listBounds(base,index);generated=extract(value->type,base,listOffset(value->args[0]->type,index));}break;
      }
      case Expr::Field:{
        auto base=expression(value->args.at(0),scope);const auto fields=values.fields(value->args[0]->type);unsigned offset=0;
        for(int64_t i=0;i<value->number;++i)offset+=values.words(fields.at(size_t(i)));
        generated=extract(value->type,base,offset);break;
      }
      case Expr::Propagate:{
        const auto input=expression(value->args.at(0),scope);line("if ("+input+".w[0] == 0LL) {");++indentation;
        auto code=extract(Type::Str,input,1),message=extract(Type::Str,input,1+values.words(Type::Str));const auto failed=construct(result,{code,message},0);line("return "+failed+";");--indentation;line("}");generated=extract(value->type,input,1);break;
      }
      case Expr::Name:{
        auto found=scope.find(value->text);
        if(found==scope.end())throw Error("E_GPU_UNSUPPORTED","unbound CUDA local: "+value->text,value->span);
        generated=found->second;break;
      }
      case Expr::Match:return matching(value,scope);
      case Expr::Unary:{
        auto child=expression(value->args.at(0),scope);
        generated=value->text=="-"?std::string(value->type==Type::F64?"nex_f_neg(":"nex_neg(")+child+", nex_s)":"!"+child;break;
      }
      case Expr::Binary:{
        auto left=expression(value->args.at(0),scope);
        if(value->text=="&&"||value->text=="||"){
          auto name=temporary();line("bool "+name+" = "+left+";");
          line("if ("+std::string(value->text=="||"?"!":"")+name+") {");++indentation;
          auto right=expression(value->args.at(1),scope);line(name+" = "+right+";");--indentation;line("}");return name;
        }
        auto right=expression(value->args.at(1),scope);
        static const std::map<std::string,std::string> helpers={{"+","add"},{"-","sub"},{"*","mul"},{"/","div"},{"%","mod"}};
        auto helper=helpers.find(value->text);
        if(value->type==Type::Str&&value->text=="+"){textLimit(left+".w[0]+"+right+".w[0]");generated="nex_text_concat("+left+", "+right+")";break;}
        if(value->type==Type::Bytes&&value->text=="+"){
          const auto length=left+".w[0]+"+right+".w[0]";byteLimit(length);const auto name=temporary();line(deviceType(Type::Bytes,where)+" "+name+" = "+left+";");line(name+".w[0] = "+length+";");
          line("for(unsigned i=0;i<static_cast<unsigned>("+right+".w[0]);++i) nex_byte_put("+name+",static_cast<unsigned long long>("+left+".w[0])+i,nex_byte_get("+right+",i));");return name;
        }
        if(value->type.kind==Type::List&&value->text=="+"){
          const auto length=left+".w[0]+"+right+".w[0]";listLimit(length);const auto name=temporary();line(deviceType(value->type,where)+" "+name+" = "+left+";");line(name+".w[0] = "+length+";");
          const auto width=std::to_string(values.words(*value->type.element));line("for(unsigned i=0;i<static_cast<unsigned>("+right+".w[0])*"+width+"U;++i) "+name+".w[1U+static_cast<unsigned>("+left+".w[0])*"+width+"U+i] = "+right+".w[1U+i];");return name;
        }
        if(values.aggregate(value->args[0]->type))generated=std::string(value->text=="!="?"!":"")+"nex_equal_"+values.cpp(value->args[0]->type)+"("+left+", "+right+")";
        else if(value->args[0]->type==Type::F64&&helper==helpers.end()){
          static const std::map<std::string,unsigned> comparisons={{"==",0},{"!=",1},{"<",2},{"<=",3},{">",4},{">=",5}};
          generated="nex_f_compare("+left+", "+right+", "+std::to_string(comparisons.at(value->text))+"U)";
        }else generated=helper==helpers.end()?left+" "+value->text+" "+right:"nex_"+std::string(value->type==Type::F64?"f_":"")+helper->second+"("+left+", "+right+", nex_s)";break;
      }
      case Expr::Call:{
        std::vector<std::string> arguments;
        for(const auto &argument:value->args){auto item=expression(argument,scope);arguments.push_back(argument->type==Type::Unit?"NexUnit{}":item);}
        if(value->text=="assert"){
          line("if (!"+arguments.at(0)+") { nex_s.code = 3; "+stop()+" }");return {};
        }
        if(value->text=="ok")return construct(value->type,arguments,1);
        if(value->text=="err")return construct(value->type,arguments,0);
        if(value->text=="bytes")return byteConstruction(value->type,arguments.at(0));
        if(values.hasText){
          if(value->text=="decode_utf8"||value->text=="decode_base64")return decodeText(value->type,arguments.at(0),value->text=="decode_utf8");
          if(value->text=="utf8_bytes"){byteLimit(arguments[0]+".w[0]");generated="nex_octet_slice<"+values.cpp(Type::Bytes)+">("+arguments[0]+", 0U, static_cast<unsigned>("+arguments[0]+".w[0]))";break;}
          if(value->text=="encode_base64"){textLimit("(("+arguments[0]+".w[0]+2LL)/3LL)*4LL");generated="nex_base64_encode<"+values.cpp(Type::Str)+">("+arguments[0]+")";break;}
          if(value->text=="str"){generated=std::string(value->args[0]->type==Type::Bool?"nex_boolean_text<":"nex_integer_text<")+values.cpp(Type::Str)+">("+arguments[0]+", "+std::to_string(values.textCapacity)+"U, nex_s)";break;}
        }
        if(value->text=="utf8_bytes"){generated="nex_utf8_bytes("+arguments.at(0)+", nex_s)";break;}
        if(value->text=="decode_base64"){generated="nex_decode_base64("+arguments.at(0)+", nex_s)";break;}
        if(value->text=="as_i64"){generated="nex_f_to_integer("+arguments.at(0)+", nex_s)";break;}
        if(value->text=="is_ok"){generated="("+arguments.at(0)+".w[0] == 1LL)";break;}
        if(value->text=="error_code"||value->text=="error_message"){
          if(values.hasText){const auto name=temporary();line(values.cpp(Type::Str)+" "+name+"{};");line("if ("+arguments[0]+".w[0] == 0LL) {");++indentation;auto text=extract(Type::Str,arguments[0],value->text=="error_code"?1:1+values.words(Type::Str));line(name+" = "+text+";");--indentation;line("}");return name;}
          generated="("+arguments.at(0)+".w[0] == 1LL ? 0U : static_cast<unsigned int>("+arguments.at(0)+".w["+std::string(value->text=="error_code"?"1":"2")+"]))";break;
        }
        if(value->text=="unwrap"){
          const auto input=arguments.at(0);
          if(values.hasText){line("if ("+input+".w[0] == 0LL) {");++indentation;line("for(unsigned i=0;i<"+std::to_string(2*values.words(Type::Str))+"U;++i)nex_s.diagnostic[i] = "+input+".w[1U+i];");line("nex_s.code = 15; "+stop());--indentation;line("}");}
          else line("if ("+input+".w[0] == 0LL) { nex_s.code = 0x80000000U | (static_cast<unsigned int>("+input+".w[1]) << 10U) | static_cast<unsigned int>("+input+".w[2]); "+stop()+" }");generated=extract(value->type,input,1);break;
        }
        if(value->text=="len"){generated=value->args[0]->type!=Type::Str?arguments.at(0)+".w[0]":values.hasText?"nex_unicode_length("+arguments[0]+")":"nex_text_length("+arguments.at(0)+", nex_s)";break;}
        if(value->text=="slice"){
          const auto &input=arguments[0],&start=arguments[1],&count=arguments[2];
          if(value->type==Type::Str){
            auto length=temporary(),offset=temporary(),end=temporary();line("long long "+length+" = nex_unicode_length("+input+");");line("if ("+start+" < 0LL || "+count+" < 0LL || "+start+" > "+length+" || "+count+" > "+length+"-"+start+") { nex_s.code = 17; "+stop()+" }");line("unsigned "+offset+" = nex_unicode_offset("+input+", static_cast<unsigned>("+start+"));");line("unsigned "+end+" = nex_unicode_offset("+input+", static_cast<unsigned>("+start+"+"+count+"));");generated="nex_octet_slice<"+values.cpp(Type::Str)+">("+input+", "+offset+", "+end+"-"+offset+")";break;
          }
          line("if ("+start+" < 0LL || "+count+" < 0LL || "+start+" > "+input+".w[0] || "+count+" > "+input+".w[0]-"+start+") { nex_s.code = 12; "+stop()+" }");
          const auto name=temporary();line(deviceType(Type::Bytes,where)+" "+name+"{};");line(name+".w[0] = "+count+";");line("for(unsigned i=0;i<static_cast<unsigned>("+count+");++i) nex_byte_put("+name+",i,nex_byte_get("+input+",static_cast<unsigned long long>("+start+")+i));");return name;
        }
        if(value->text=="push"||value->text=="set"){
          const auto &input=arguments.at(0);const bool push=value->text=="push";
          const auto index=push?input+".w[0]":arguments.at(1);
          if(value->type==Type::Bytes){
            const auto &octet=arguments.at(push?1:2);if(!push)byteBounds(input,index);byteRange(octet);if(push)byteLimit(index+"+1LL");
            const auto name=temporary();line(deviceType(Type::Bytes,where)+" "+name+" = "+input+";");line("nex_byte_put("+name+",static_cast<unsigned long long>("+index+"),"+octet+");");if(push)line(name+".w[0] = "+index+"+1LL;");return name;
          }
          if(push)listLimit(index+"+1LL");else listBounds(input,index);
          const auto name=temporary();line(deviceType(value->type,where)+" "+name+" = "+input+";");
          insert(*value->type.element,arguments.at(push?1:2),name,listOffset(value->type,index));
          if(push)line(name+".w[0] = "+index+"+1LL;");return name;
        }
        if(program.variant(value->text))return construct(value->type,arguments,value->number);
        if(program.hasStructure(value->text))return construct(value->type,arguments);
        if(value->text=="as_f64"){generated="nex_f_from_integer("+arguments.at(0)+", nex_s)";break;}
        generated=names.at(value->text)+"(";
        for(const auto &argument:arguments)generated+=argument+", ";
        generated+="nex_s)";break;
      }
      default:throw Error("E_GPU_UNSUPPORTED","unsupported CUDA expression",value->span);
    }
    if(value->type==Type::Unit){line(generated+";");guard();return {};}
    auto name=temporary();line(deviceType(value->type,value->span)+" "+name+" = "+generated+";");guard();return name;
  }

  void block(const std::vector<S> &statements,Scope scope){
    for(const auto &statement:statements){
      where=statement->span;tick();
      switch(statement->kind){
        case Stmt::Let:case Stmt::Var:{
          auto value=expression(statement->expr,scope),name=temporary();
          if(statement->type==Type::Unit)value="NexUnit{}";
          line(deviceType(statement->type,statement->span)+" "+name+" = "+value+";");scope[statement->name]=name;break;
        }
        case Stmt::Assign:{
          auto value=expression(statement->expr,scope);auto found=scope.find(statement->name);
          if(found==scope.end())throw Error("E_GPU_UNSUPPORTED","unbound CUDA assignment",statement->span);
          line(found->second+" = "+value+";");break;
        }
        case Stmt::Expression:expression(statement->expr,scope);break;
        case Stmt::Match:expression(statement->expr,scope);break;
        case Stmt::Return:{
          auto value=statement->expr?expression(statement->expr,scope):std::string{};
          line("return"+(value.empty()?std::string{}:" "+value)+";");break;
        }
        case Stmt::If:{
          auto condition=expression(statement->expr,scope);line("if ("+condition+") {");++indentation;block(statement->body,scope);
          --indentation;line("} else {");++indentation;block(statement->alternative,scope);--indentation;line("}");break;
        }
        case Stmt::While:{
          line("while (true) {");++indentation;auto condition=expression(statement->expr,scope);
          line("if (!"+condition+") break;");block(statement->body,scope);--indentation;line("}");break;
        }
        default:throw Error("E_GPU_UNSUPPORTED","unsupported CUDA statement",statement->span);
      }
    }
  }

  void kernelValues(){
    where=root.span;line("extern \"C\" __global__ void nex_generated_cuda_map(");
    if(layout=="rows")line("  const long long *input,");else for(size_t i=0;i<root.params.size();++i)line("  const long long *input_"+std::to_string(i)+",");
    line(std::string("  long long *output, unsigned int *errors, ")+(values.hasText?"long long *diagnostics, ":"")+"unsigned int lanes, unsigned int steps) {");++indentation;
    line("const unsigned long long lane = static_cast<unsigned long long>(blockIdx.x) * blockDim.x + threadIdx.x;");line("if (lane >= static_cast<unsigned long long>(lanes)) return;");
    if(values.hasText){const auto width=std::to_string(2*values.words(Type::Str));line("long long *diagnostic = diagnostics + lane * "+width+"ULL;");line("for(unsigned i=0;i<"+width+"U;++i)diagnostic[i]=0LL;");line("NexState nex_s = {0, steps, diagnostic};");}else line("NexState nex_s = {0, steps};");
    unsigned rowWords=0;for(const auto &p:root.params)rowWords+=values.words(p.type);unsigned offset=0;std::vector<std::string> arguments;
    for(size_t i=0;i<root.params.size();++i){const auto &p=root.params[i];auto name="nex_input_"+std::to_string(i);const auto width=values.words(p.type);
      const auto address=layout=="rows"?"input[lane * "+std::to_string(rowWords)+"ULL + "+std::to_string(offset)+"ULL":"input_"+std::to_string(i)+"[lane * "+std::to_string(width)+"ULL";
      line(deviceType(p.type,p.span)+" "+name+"{};");
      if(values.aggregate(p.type)){line("for(unsigned i=0;i<"+std::to_string(width)+"U;++i) "+name+".w[i] = "+address+" + i];");line(name+" = "+values.normalizer(p.type)+"("+name+", nex_s);");}
      else{auto word=name+"_word";line("long long "+word+" = "+address+"];");
        if(p.type==Type::Bool)line("if (!nex_s.code && "+word+" != 0LL && "+word+" != 1LL) nex_s.code = 6;");
        if(p.type==Type::Str)line("if (!nex_s.code && nex_unsigned("+word+") >= "+std::to_string(values.idMax())+"ULL) nex_s.code = 6;");
        if(p.type==Type::Unit)line("if (!nex_s.code && "+word+" != 0LL) nex_s.code = 6;");
        line(name+" = "+values.load(p.type,word)+";");
      }
      arguments.push_back(name);offset+=width;
    }
    const auto width=values.words(root.result);if(root.result!=Type::Unit)line(deviceType(root.result,root.span)+" nex_result{};");
    auto call=names.at(root.name)+"(";for(const auto &arg:arguments)call+=arg+", ";call+="nex_s)";
    line("if (!nex_s.code) {");++indentation;line(std::string(root.result==Type::Unit?"":"nex_result = ")+call+";");--indentation;line("}");
    if(values.aggregate(root.result))line("for(unsigned i=0;i<"+std::to_string(width)+"U;++i) output[lane * "+std::to_string(width)+"ULL+i] = nex_s.code ? 0LL : nex_result.w[i];");
    else line("output[lane] = nex_s.code ? 0LL : "+values.store(root.result,"nex_result")+";");
    line("errors[lane] = nex_s.code;");--indentation;line("}");
  }

public:
  Emitter(const Program &program,const std::string &entry,const std::string &inputLayout,unsigned capacity,unsigned byteCapacity,unsigned textCapacity)
      :program(program),root(program.function(entry)),values(program,capacity,byteCapacity,textCapacity),layout(inputLayout),where(root.span){
    if(layout!="rows"&&layout!="columns")throw Error("E_OPTION","CUDA input layout must be rows or columns");
    if(std::string(programLanguage(program))!="0.28")throw Error("E_GPU_UNSUPPORTED","CUDA emission requires checked language0.28",root.span);
    for(const auto &function:program.functions)functions.emplace(function.name,&function);
    discover(root,root.span);values.finalize();
    if(root.params.size()>8)throw Error("E_GPU_LIMIT","CUDA root has more than8 scalar arguments",root.span);
    for(size_t i=0;i<order.size();++i)names.emplace(order[i]->name,"nex_fn_"+std::to_string(i));
  }

  CudaSource generate(){
    CudaSource emission;emission.entry=root.name;emission.inputLayout=layout;emission.resultType=typeName(root.result);
    for(const auto &parameter:root.params)emission.parameterTypes.push_back(typeName(parameter.type));
    auto runtimeSource=std::string(runtime);
    if(values.hasText){const auto at=runtimeSource.find("unsigned int remaining; }");runtimeSource.replace(at,std::string("unsigned int remaining; }").size(),"unsigned int remaining; long long *diagnostic; }");}
    const auto valuePrefix=values.prelude();valuePrefixBytes=valuePrefix.size()+runtimeSource.size()-runtime.size();
    if(runtime.size()+valuePrefixBytes+(floatingPoint?cuda_detail::floatingRuntime.size():0)+1>=maximumSourceBytes)throw Error("E_GPU_LIMIT","CUDA value prelude exceeds16MiB",root.span);
    const auto prefix=runtimeSource+(floatingPoint?std::string(cuda_detail::floatingRuntime):std::string{})+valuePrefix;
    emission.valueABI=values.metadata(root.params,root.result);
    const auto prefixLines=unsigned(std::count(prefix.begin(),prefix.end(),'\n'))+1;
    emission.floatingPoint=floatingPoint;
    for(const auto *function:order){
      result=function->result;where=function->span;Scope scope;
      CudaSourceFunction metadata{function->name,names.at(function->name),hash(json(canonical(*function),false)),function->span,prefixLines+lines+1,0};
      auto signature=(result==Type::Unit?"void":deviceType(result,function->span))+" "+metadata.symbol+"(";
      for(size_t i=0;i<function->params.size();++i){
        const auto &parameter=function->params[i];auto name="nex_p_"+std::to_string(i);scope[parameter.name]=name;
        signature+=deviceType(parameter.type,parameter.span)+(values.aggregate(parameter.type)?" const & ":" ")+name+", ";
      }
      line("__device__ "+signature+"NexState &nex_s) {");++indentation;block(function->body,scope);
      if(result==Type::Unit)line("return;");else line("nex_s.code = 5; "+stop());
      --indentation;line("}");metadata.lastLine=prefixLines+lines;emission.functions.push_back(std::move(metadata));
    }
    if(values.extended){kernelValues();emission.source=prefix+"\n"+text;return emission;}
    where=root.span;
    line("extern \"C\" __global__ void nex_generated_cuda_map(");
    if(layout=="rows")line("  const long long *input,");
    else for(size_t i=0;i<root.params.size();++i)
      line("  const long long *input_"+std::to_string(i)+",");
    line("  long long *output, unsigned int *errors, unsigned int lanes, unsigned int steps) {");
    ++indentation;
    line("const unsigned long long lane = static_cast<unsigned long long>(blockIdx.x) * blockDim.x + threadIdx.x;");
    line("if (lane >= static_cast<unsigned long long>(lanes)) return;");
    line("NexState nex_s = {0, steps};");
    std::vector<std::string> arguments;
    for(size_t i=0;i<root.params.size();++i){
      auto name="nex_input_"+std::to_string(i);
      auto address=layout=="rows"?"input[lane * "+std::to_string(root.params.size())+"ULL + "+std::to_string(i)+"ULL]":"input_"+std::to_string(i)+"[lane]";
      line("long long "+name+" = "+address+";");
      if(root.params[i].type==Type::Bool){line("if ("+name+" != 0LL && "+name+" != 1LL"+std::string(floatingPoint?" && !nex_s.code":"")+") nex_s.code = 6;");arguments.push_back("("+name+" != 0LL)");}
      else if(root.params[i].type==Type::F64){auto decoded=name+"_float";line("double "+decoded+" = nex_f_value(nex_unsigned("+name+"), nex_s);");arguments.push_back(decoded);}
      else arguments.push_back(name);
    }
    line("long long nex_result = 0LL;");auto call=names.at(root.name)+"(";
    for(const auto &argument:arguments)call+=argument+", ";call+="nex_s)";
    if(root.result==Type::F64)call="nex_bits(nex_f_bits("+call+"))";
    line("if (!nex_s.code) {");++indentation;line(std::string(root.result==Type::Unit?"":"nex_result = ")+call+";");--indentation;line("}");
    line("output[lane] = nex_s.code ? 0LL : nex_result;");line("errors[lane] = nex_s.code;");--indentation;line("}");
    emission.source=prefix+"\n"+text;return emission;
  }
};
}
CudaSource emitCuda(const Program &program,const std::string &entry,const std::string &inputLayout,unsigned capacity,unsigned byteCapacity,unsigned textCapacity){
  return Emitter(program,entry,inputLayout,capacity,byteCapacity,textCapacity).generate();
}
}
