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
    else if(pattern->kind!=Pattern::Binding&&pattern->kind!=Pattern::Wildcard&&pattern->kind!=Pattern::Integer&&pattern->kind!=Pattern::Boolean&&pattern->kind!=Pattern::Constructor)
      throw Error("E_GPU_UNSUPPORTED","unsupported CUDA value pattern",pattern->span);
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
      case Expr::Unary:
        if(expression->args.size()!=1||(expression->text!="-"&&expression->text!="!"))
          throw Error("E_GPU_UNSUPPORTED","unsupported CUDA unary expression",expression->span);
        break;
      case Expr::Binary:{
        static const std::set<std::string> operators={"+","-","*","/","%","==","!=","<","<=",">",">=","&&","||"};
        if(expression->args.size()!=2||!operators.contains(expression->text))
          throw Error("E_GPU_UNSUPPORTED","unsupported CUDA binary expression",expression->span);
        if(expression->args[0]->type.heap()&&expression->text!="=="&&expression->text!="!=")
          throw Error("E_GPU_UNSUPPORTED","device values support equality; dynamic heap/text arithmetic is unavailable",expression->span);
        break;
      }
      case Expr::Call:
        if(expression->text=="as_i64"){
          values.conversion=true;values.literal("E_RANGE",expression->span);values.literal("f64 value is outside i64 range",expression->span);
        }else if(expression->text=="ok"||expression->text=="err"||expression->text=="is_ok"||expression->text=="unwrap"||expression->text=="error_code"||expression->text=="error_message"||expression->text=="len"||program.hasStructure(expression->text)||program.variant(expression->text)){
          if(expression->text=="len"&&expression->args[0]->type!=Type::Str)throw Error("E_GPU_TYPE","device len currently requires bounded text",expression->span);
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
      case Pattern::String:return subject+" == "+std::to_string(values.id(pattern->text))+"U";
      case Pattern::Boolean:return subject+" == "+(pattern->number?"true":"false");
      case Pattern::Integer:{
        std::ostringstream bits;bits<<std::hex<<std::setfill('0')<<std::setw(16)<<static_cast<uint64_t>(pattern->number);
        return subject+" == nex_bits(0x"+bits.str()+"ULL)";
      }
      default:throw Error("E_GPU_UNSUPPORTED","unsupported CUDA scalar pattern",pattern->span);
    }
  }

  std::string extract(const Type &type,const std::string &base,unsigned offset){
    if(!values.aggregate(type))return values.load(type,base+".w["+std::to_string(offset)+"]");
    const auto name=temporary();line(deviceType(type,where)+" "+name+"{};");
    line("for(unsigned i=0;i<"+std::to_string(values.words(type))+"U;++i) "+name+".w[i] = "+base+".w["+std::to_string(offset)+"U+i];");return name;
  }
  void insert(const Type &type,const std::string &value,const std::string &base,unsigned offset){
    if(values.aggregate(type))line("for(unsigned i=0;i<"+std::to_string(values.words(type))+"U;++i) "+base+".w["+std::to_string(offset)+"U+i] = "+value+".w[i];");
    else line(base+".w["+std::to_string(offset)+"] = "+values.store(type,value)+";");
  }
  std::string construct(const Type &type,const std::vector<std::string> &arguments,int64_t tag=0){
    const auto name=temporary();line(deviceType(type,where)+" "+name+"{};");
    unsigned offset=values.payloadOffset(type);if(offset)line(name+".w[0] = "+std::to_string(tag)+"LL;");
    const auto fs=values.fields(type,tag);for(size_t i=0;i<fs.size();++i){insert(fs[i],arguments.at(i),name,offset);offset+=values.words(fs[i]);}return name;
  }
  void pattern(const P &p,const std::string &subject,const std::string &accepted,Scope &bound){
    line("if ("+accepted+") {");++indentation;
    if(p->kind==Pattern::Binding)line(bound.at(p->text)+" = "+subject+";");
    else if(p->kind==Pattern::Constructor){
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
      case Expr::String:generated=std::to_string(values.id(value->text))+"U";break;
      case Expr::Field:{
        auto base=expression(value->args.at(0),scope);const auto fields=values.fields(value->args[0]->type);unsigned offset=0;
        for(int64_t i=0;i<value->number;++i)offset+=values.words(fields.at(size_t(i)));
        generated=extract(value->type,base,offset);break;
      }
      case Expr::Propagate:{
        const auto input=expression(value->args.at(0),scope);line("if ("+input+".w[0] == 0LL) {");++indentation;
        const auto failed=construct(result,{"static_cast<unsigned int>("+input+".w[1])","static_cast<unsigned int>("+input+".w[2])"},0);line("return "+failed+";");--indentation;line("}");generated=extract(value->type,input,1);break;
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
        if(value->text=="as_i64"){generated="nex_f_to_integer("+arguments.at(0)+", nex_s)";break;}
        if(value->text=="is_ok"){generated="("+arguments.at(0)+".w[0] == 1LL)";break;}
        if(value->text=="error_code"||value->text=="error_message"){generated="("+arguments.at(0)+".w[0] == 1LL ? 0U : static_cast<unsigned int>("+arguments.at(0)+".w["+std::string(value->text=="error_code"?"1":"2")+"]))";break;}
        if(value->text=="unwrap"){
          const auto input=arguments.at(0);line("if ("+input+".w[0] == 0LL) { nex_s.code = 0x80000000U | (static_cast<unsigned int>("+input+".w[1]) << 10U) | static_cast<unsigned int>("+input+".w[2]); "+stop()+" }");generated=extract(value->type,input,1);break;
        }
        if(value->text=="len"){generated="nex_text_length("+arguments.at(0)+", nex_s)";break;}
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
    line("  long long *output, unsigned int *errors, unsigned int lanes, unsigned int steps) {");++indentation;
    line("const unsigned long long lane = static_cast<unsigned long long>(blockIdx.x) * blockDim.x + threadIdx.x;");line("if (lane >= static_cast<unsigned long long>(lanes)) return;");line("NexState nex_s = {0, steps};");
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
  Emitter(const Program &program,const std::string &entry,const std::string &inputLayout)
      :program(program),root(program.function(entry)),values(program),layout(inputLayout),where(root.span){
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
    const auto valuePrefix=values.prelude();valuePrefixBytes=valuePrefix.size();
    if(runtime.size()+valuePrefixBytes+(floatingPoint?cuda_detail::floatingRuntime.size():0)+1>=maximumSourceBytes)throw Error("E_GPU_LIMIT","CUDA value prelude exceeds16MiB",root.span);
    const auto prefix=std::string(runtime)+(floatingPoint?std::string(cuda_detail::floatingRuntime):std::string{})+valuePrefix;
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
CudaSource emitCuda(const Program &program,const std::string &entry,const std::string &inputLayout){
  return Emitter(program,entry,inputLayout).generate();
}
}
