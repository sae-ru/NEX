#include "nex/opencl.h"
#include <algorithm>
#include <iomanip>
#include <sstream>
#include <string_view>

namespace nex {
namespace {
constexpr std::string_view runtime=R"nexopencl(// NEX OpenCL C 1.2 scalar kernel runtime.
typedef struct { uint code; uint remaining; } NexState;
inline long nex_bits(ulong x) { union { ulong u; long s; } v; v.u = x; return v.s; }
inline ulong nex_unsigned(long x) { union { ulong u; long s; } v; v.s = x; return v.u; }
inline bool nex_tick(__private NexState *s) {
  if (s->code) return false;
  if (!s->remaining) { s->code = 4; return false; }
  --s->remaining;
  return true;
}
inline long nex_add(long a, long b, __private NexState *s) {
  ulong x = nex_unsigned(a), y = nex_unsigned(b), z = x + y;
  if (((x ^ z) & (y ^ z) & 0x8000000000000000UL) != 0) { s->code = 1; return 0; }
  return nex_bits(z);
}
inline long nex_sub(long a, long b, __private NexState *s) {
  ulong x = nex_unsigned(a), y = nex_unsigned(b), z = x - y;
  if (((x ^ y) & (x ^ z) & 0x8000000000000000UL) != 0) { s->code = 1; return 0; }
  return nex_bits(z);
}
inline long nex_neg(long a, __private NexState *s) {
  ulong x = nex_unsigned(a);
  if (x == 0x8000000000000000UL) { s->code = 1; return 0; }
  return nex_bits(0UL - x);
}
inline ulong nex_magnitude(long x) {
  ulong bits = nex_unsigned(x);
  return x < 0 ? 0UL - bits : bits;
}
inline long nex_mul(long a, long b, __private NexState *s) {
  bool negative = (a < 0) != (b < 0);
  ulong x = nex_magnitude(a), y = nex_magnitude(b);
  ulong limit = negative ? 0x8000000000000000UL : 0x7fffffffffffffffUL;
  if (x && y > limit / x) { s->code = 1; return 0; }
  ulong product = x * y;
  return nex_bits(negative ? 0UL - product : product);
}
inline long nex_div(long a, long b, __private NexState *s) {
  if (!b) { s->code = 2; return 0; }
  if (nex_unsigned(a) == 0x8000000000000000UL && b == -1L) { s->code = 1; return 0; }
  ulong value = nex_magnitude(a) / nex_magnitude(b);
  return nex_bits((a < 0) != (b < 0) ? 0UL - value : value);
}
inline long nex_mod(long a, long b, __private NexState *s) {
  if (!b) { s->code = 2; return 0; }
  ulong value = nex_magnitude(a) % nex_magnitude(b);
  return nex_bits(a < 0 ? 0UL - value : value);
}
)nexopencl";
constexpr std::string_view floatRuntime=R"nexfp64(inline double nex_f_bits(ulong x) { union { ulong u; double d; } v; v.u = x; return v.d; }
inline ulong nex_f_unsigned(double x) { union { ulong u; double d; } v; v.d = x; return v.u; }
inline double nex_f_add(double a, double b, __private NexState *s) { double r = a + b; if (!isfinite(r)) s->code = 7; return r; }
inline double nex_f_sub(double a, double b, __private NexState *s) { double r = a - b; if (!isfinite(r)) s->code = 7; return r; }
inline double nex_f_mul(double a, double b, __private NexState *s) { double r = a * b; if (!isfinite(r)) s->code = 7; return r; }
inline double nex_f_div(double a, double b, __private NexState *s) { if (!b) { s->code = 2; return 0.0; } double r = a / b; if (!isfinite(r)) s->code = 7; return r; }
inline double nex_f_neg(double a, __private NexState *s) { double r = -a; if (!isfinite(r)) s->code = 7; return r; }
inline double nex_f_from_integer(long x) { return (double)x; }
)nexfp64";
constexpr size_t maximumSourceBytes=16*1024*1024;

std::string scalar(const Type &type,Span span){
  switch(type.kind){
    case Type::I64:return "long";
    case Type::F64:return "double";
    case Type::Bool:return "bool";
    case Type::Unit:return "void";
    default:throw Error("E_GPU_TYPE","OpenCL scalar emission does not support "+typeName(type),span);
  }
}

class Emitter {
  const Function &root;
  std::string layout,text;
  std::map<std::string,const Function*> functions;
  std::map<std::string,std::string> names;
  std::set<std::string> visiting,visited;
  std::vector<const Function*> order;
  unsigned indentation=0,serial=0,lines=0;
  Type result=Type::Unit;bool usesFloat=false;
  Span where;
  using Scope=std::map<std::string,std::string>;

  void discover(const Function &function,Span caller){
    if(visiting.contains(function.name))throw Error("E_GPU_RECURSION","recursive OpenCL call graph: "+function.name,caller);
    if(visited.contains(function.name))return;
    if(visiting.size()>=128)throw Error("E_GPU_LIMIT","OpenCL call depth exceeds128 functions",caller);
    if(function.realm!="shared"||!function.effects.empty())
      throw Error("E_GPU_REALM","OpenCL functions must be shared and pure: "+function.name,function.span);
    if(function.foreign||function.closure||!function.captures.empty()||!function.typeParameters.empty())
      throw Error("E_GPU_UNSUPPORTED","OpenCL functions must be concrete, without captures or foreign authority",function.span);
    if(function.result==Type::F64)usesFloat=true;
    scalar(function.result,function.span);
    for(const auto &parameter:function.params){
      if(parameter.type==Type::Unit)throw Error("E_GPU_TYPE","unit is not a OpenCL argument",parameter.span);
      scalar(parameter.type,parameter.span);
    }
    visiting.insert(function.name);
    validateBlock(function.body);
    visiting.erase(function.name);visited.insert(function.name);order.push_back(&function);
    if(order.size()>128)throw Error("E_GPU_LIMIT","OpenCL call graph exceeds128 functions",function.span);
  }

  void validateExpression(const E &expression){
    if(!expression)return;
    if(expression->type==Type::F64)usesFloat=true;
    scalar(expression->type,expression->span);
    switch(expression->kind){
      case Expr::Integer:case Expr::Floating:case Expr::Boolean:case Expr::Name:break;
      case Expr::Unary:
        if(expression->args.size()!=1||(expression->text!="-"&&expression->text!="!"))
          throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL unary expression",expression->span);
        break;
      case Expr::Binary:{
        static const std::set<std::string> operators={"+","-","*","/","%","==","!=","<","<=",">",">=","&&","||"};
        if(expression->args.size()!=2||!operators.contains(expression->text))
          throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL binary expression",expression->span);
        break;
      }
      case Expr::Call:
        if(expression->text!="assert"){
          auto found=functions.find(expression->text);
          if(found==functions.end())throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL builtin or callee: "+expression->text,expression->span);
          discover(*found->second,expression->span);
        }else if(expression->args.size()!=1||expression->type!=Type::Unit)
          throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL assertion",expression->span);
        break;
      default:throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL expression",expression->span);
    }
    for(const auto &argument:expression->args)validateExpression(argument);
  }

  void validateBlock(const std::vector<S> &statements){
    for(const auto &statement:statements){
      switch(statement->kind){
        case Stmt::Let:case Stmt::Var:
          if(statement->type==Type::Unit)throw Error("E_GPU_TYPE","unit is not a OpenCL local",statement->span);
          if(statement->type==Type::F64)usesFloat=true;
          scalar(statement->type,statement->span);break;
        case Stmt::Assign:case Stmt::Expression:case Stmt::Return:case Stmt::If:case Stmt::While:break;
        default:throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL statement",statement->span);
      }
      validateExpression(statement->expr);
      validateBlock(statement->body);validateBlock(statement->alternative);
    }
  }

  void line(const std::string &value){
    const size_t extra=2*indentation+value.size()+1;
    if(extra>maximumSourceBytes-text.size()-runtime.size()-1)
      throw Error("E_GPU_LIMIT","generated OpenCL source exceeds16MiB",where);
    text.append(2*indentation,' ');text+=value;text+='\n';++lines;
  }
  std::string temporary(){return "nex_v_"+std::to_string(++serial);}
  std::string stop()const{return result==Type::Unit?"return;":std::string("return ")+(result==Type::Bool?"false":result==Type::F64?"0.0":"0L")+";";}
  void guard(){line("if (s->code) { "+stop()+" }");}
  void tick(){line("if (!nex_tick(s)) { "+stop()+" }");}

  std::string expression(const E &value,const Scope &scope){
    if(!value)throw Error("E_GPU_UNSUPPORTED","missing OpenCL expression",where);
    where=value->span;tick();std::string generated;
    switch(value->kind){
      case Expr::Integer:{
        std::ostringstream bits;bits<<std::hex<<std::setfill('0')<<std::setw(16)<<static_cast<uint64_t>(value->number);
        generated="nex_bits(0x"+bits.str()+"UL)";break;
      }
      case Expr::Floating:{
        std::ostringstream bits;bits<<std::hex<<std::setfill('0')<<std::setw(16)<<static_cast<uint64_t>(value->number);
        generated="nex_f_bits(0x"+bits.str()+"UL)";break;
      }
      case Expr::Boolean:generated=value->number?"true":"false";break;
      case Expr::Name:{
        auto found=scope.find(value->text);
        if(found==scope.end())throw Error("E_GPU_UNSUPPORTED","unbound OpenCL local: "+value->text,value->span);
        generated=found->second;break;
      }
      case Expr::Unary:{
        auto child=expression(value->args.at(0),scope);
        generated=value->text=="-"?(value->type==Type::F64?"nex_f_neg("+child+", s)":"nex_neg("+child+", s)"):"!"+child;break;
      }
      case Expr::Binary:{
        auto left=expression(value->args.at(0),scope);
        if(value->text=="&&"||value->text=="||"){
          auto name=temporary();line("bool "+name+" = "+left+";");
          line("if ("+std::string(value->text=="||"?"!":"")+name+") {");++indentation;
          auto right=expression(value->args.at(1),scope);line(name+" = "+right+";");--indentation;line("}");return name;
        }
        auto right=expression(value->args.at(1),scope);
        if(value->type==Type::F64){
          if(value->text=="%"||value->text=="&&"||value->text=="||")throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL f64 operator",value->span);
          static const std::map<std::string,std::string> floatHelpers={{"+","f_add"},{"-","f_sub"},{"*","f_mul"},{"/","f_div"}};
          auto helper=floatHelpers.find(value->text);
          generated=helper==floatHelpers.end()?left+" "+value->text+" "+right:"nex_"+helper->second+"("+left+", "+right+", s)";break;
        }
        static const std::map<std::string,std::string> helpers={{"+","add"},{"-","sub"},{"*","mul"},{"/","div"},{"%","mod"}};
        auto helper=helpers.find(value->text);
        generated=helper==helpers.end()?left+" "+value->text+" "+right:"nex_"+helper->second+"("+left+", "+right+", s)";break;
      }
      case Expr::Call:{
        std::vector<std::string> arguments;
        for(const auto &argument:value->args)arguments.push_back(expression(argument,scope));
        if(value->text=="as_f64"&&arguments.size()==1&&value->args[0]->type==Type::I64){generated="nex_f_from_integer("+arguments[0]+")";break;}
        if(value->text=="assert"){
          line("if (!"+arguments.at(0)+") { s->code = 3; "+stop()+" }");return {};
        }
        generated=names.at(value->text)+"(";
        for(const auto &argument:arguments)generated+=argument+", ";
        generated+="s)";break;
      }
      default:throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL expression",value->span);
    }
    if(value->type==Type::Unit){line(generated+";");guard();return {};}
    auto name=temporary();line(scalar(value->type,value->span)+" "+name+" = "+generated+";");guard();return name;
  }

  void block(const std::vector<S> &statements,Scope scope){
    for(const auto &statement:statements){
      where=statement->span;tick();
      switch(statement->kind){
        case Stmt::Let:case Stmt::Var:{
          auto value=expression(statement->expr,scope),name=temporary();
          line(scalar(statement->type,statement->span)+" "+name+" = "+value+";");scope[statement->name]=name;break;
        }
        case Stmt::Assign:{
          auto value=expression(statement->expr,scope);auto found=scope.find(statement->name);
          if(found==scope.end())throw Error("E_GPU_UNSUPPORTED","unbound OpenCL assignment",statement->span);
          line(found->second+" = "+value+";");break;
        }
        case Stmt::Expression:expression(statement->expr,scope);break;
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
        default:throw Error("E_GPU_UNSUPPORTED","unsupported OpenCL statement",statement->span);
      }
    }
  }

public:
  Emitter(const Program &program,const std::string &entry,const std::string &inputLayout)
      :root(program.function(entry)),layout(inputLayout),where(root.span){
    if(layout!="rows"&&layout!="columns")throw Error("E_OPTION","OpenCL input layout must be rows or columns");
    if(std::string(programLanguage(program))!="0.28"&&std::string(programLanguage(program))!="0.29")throw Error("E_GPU_UNSUPPORTED","OpenCL emission requires checked language0.28",root.span);
    for(const auto &function:program.functions)functions.emplace(function.name,&function);
    discover(root,root.span);
    if(root.params.size()>8)throw Error("E_GPU_LIMIT","OpenCL root has more than8 scalar arguments",root.span);
    for(size_t i=0;i<order.size();++i)names.emplace(order[i]->name,"nex_fn_"+std::to_string(i));
  }

  OpenCLSource generate(){
    OpenCLSource emission;emission.entry=root.name;emission.inputLayout=layout;emission.resultType=typeName(root.result);
    for(const auto &parameter:root.params)emission.parameterTypes.push_back(typeName(parameter.type));
    const auto prefixLines=unsigned(std::count(runtime.begin(),runtime.end(),'\n'))+1;
    for(const auto *function:order){
      result=function->result;where=function->span;Scope scope;
      OpenCLSourceFunction metadata{function->name,names.at(function->name),hash(json(canonical(*function),false)),function->span,prefixLines+lines+1,0};
      auto signature=scalar(result,function->span)+" "+metadata.symbol+"(";
      for(size_t i=0;i<function->params.size();++i){
        const auto &parameter=function->params[i];auto name="nex_p_"+std::to_string(i);scope[parameter.name]=name;
        signature+=scalar(parameter.type,parameter.span)+" "+name+", ";
      }
      line(signature+"__private NexState *s) {");++indentation;block(function->body,scope);
      if(result==Type::Unit)line("return;");else line("s->code = 5; "+stop());
      --indentation;line("}");metadata.lastLine=prefixLines+lines;emission.functions.push_back(std::move(metadata));
    }
    where=root.span;
    if(layout=="rows"){
      line("__kernel void nex_generated_map(__global const long *input,");
      line("  __global long *output, __global uint *errors, uint count, uint steps) {");
    }else{
      line("__kernel void nex_generated_map(");
      for(size_t i=0;i<root.params.size();++i)line("  __global const long *input_"+std::to_string(i)+",");
      line("  __global long *output, __global uint *errors, uint count, uint steps) {");
    }
    ++indentation;line("size_t lane = get_global_id(0);");line("if (lane >= (size_t)count) return;");
    line("NexState nex_state; nex_state.code = 0; nex_state.remaining = steps; __private NexState *s = &nex_state;");
    std::vector<std::string> arguments;
    for(size_t i=0;i<root.params.size();++i){
      auto name="nex_input_"+std::to_string(i);
      auto address=layout=="rows"?"input[lane * "+std::to_string(root.params.size())+"u + "+std::to_string(i)+"u]":"input_"+std::to_string(i)+"[lane]";
      line("long "+name+" = "+address+";");
      if(root.params[i].type==Type::Bool){line("if ("+name+" != 0L && "+name+" != 1L) s->code = 6;");arguments.push_back("("+name+" != 0L)");}
      else if(root.params[i].type==Type::F64){auto decoded=name+"_f64";line("double "+decoded+" = nex_f_bits(nex_unsigned("+name+")); if (!isfinite("+decoded+")) s->code = 7;");arguments.push_back(decoded);}
      else arguments.push_back(name);
    }
    line(root.result==Type::F64?"double nex_result = 0.0;":"long nex_result = 0L;");auto call=names.at(root.name)+"(";
    for(const auto &argument:arguments)call+=argument+", ";call+="s)";
    line("if (!s->code) {");++indentation;line(std::string(root.result==Type::Unit?"":"nex_result = ")+call+";");--indentation;line("}");
    if(root.result==Type::F64)line("output[lane] = s->code ? 0L : (long)nex_f_unsigned(nex_result);");
    else line("output[lane] = s->code ? 0L : nex_result;");
    line("errors[lane] = s->code;");--indentation;line("}");
    std::string preamble=std::string(runtime);
    if(usesFloat)preamble="#pragma OPENCL EXTENSION cl_khr_fp64 : enable\n"+preamble+"\n"+std::string(floatRuntime);
    emission.source=preamble+"\n"+text;return emission;
  }
};
}
OpenCLSource emitOpenCL(const Program &program,const std::string &entry,const std::string &inputLayout){
  return Emitter(program,entry,inputLayout).generate();
}
}
