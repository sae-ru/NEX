#include "nex/bytes_build.h"
namespace nex {
E bytesBuildLambda(const std::vector<Type> &arguments,const std::string &realm,
                   const std::set<std::string> &effects,Span span,int64_t ordinal){
  auto expression=[&](Expr::Kind kind,std::string text,std::vector<E> args=std::vector<E>{}){
    auto e=std::make_shared<Expr>();e->kind=kind;e->text=std::move(text);e->args=std::move(args);e->span=span;return e;
  };
  auto name=[&](const std::string &text){return expression(Expr::Name,text);};
  auto integer=[&](int64_t value){auto e=expression(Expr::Integer,"");e->number=value;return e;};
  auto call=[&](const std::string &target,std::vector<E> args){return expression(Expr::Call,target,std::move(args));};
  auto binary=[&](const std::string &op,E a,E b){return expression(Expr::Binary,op,{std::move(a),std::move(b)});};
  auto statement=[&](Stmt::Kind kind,E value={}){
    auto s=std::make_shared<Stmt>();s->kind=kind;s->expr=std::move(value);s->span=span;return s;
  };
  auto declaration=[&](const std::string &text,Type type,E value){
    auto s=statement(Stmt::Var,std::move(value));s->name=text;s->type=std::move(type);return s;
  };
  const std::string buffer="nex_bytes_buffer",index="nex_bytes_index",count="nex_bytes_count",state="nex_bytes_state";
  auto parameter=[](size_t index){return "nex_bytes_argument_"+std::to_string(index);};
  auto invoke=[&](size_t fn,E argument){return expression(Expr::Invoke,"",{name(parameter(fn)),std::move(argument)});};
  auto lambda=expression(Expr::Lambda,"");lambda->number=ordinal;
  lambda->lambda=std::make_shared<Function>();auto &fn=*lambda->lambda;
  fn.compilerBytesBuilder=true;fn.realm=realm;fn.effects=effects;fn.result=Type::Bytes;fn.span=span;
  for(size_t i=0;i<arguments.size();++i)fn.params.push_back({parameter(i),arguments[i],span});
  const bool generated=arguments[0]==Type::I64,stateful=arguments.size()==4,filtered=arguments.size()==3;
  fn.body.push_back(declaration(count,Type::I64,generated?name(parameter(0)):call("len",{name(parameter(0))})));
  if(generated)fn.body.push_back(statement(Stmt::Expression,call("assert",{binary(">=",name(count),integer(0))})));
  auto bufferType=Type::list(Type::I64);
  auto start=call("$list_start",{});start->annotation=bufferType;
  fn.body.push_back(declaration(buffer,bufferType,std::move(start)));
  fn.body.push_back(declaration(index,Type::I64,integer(0)));
  if(stateful)fn.body.push_back(declaration(state,arguments[1],name(parameter(1))));
  auto loop=statement(Stmt::While,binary("<",name(index),name(count)));
  auto item=[&](){return generated?name(index):expression(Expr::Index,"",{name(parameter(0)),name(index)});};
  auto emitted=stateful?invoke(3,name(state)):invoke(filtered?2:1,item());
  auto append=statement(Stmt::Expression,call("$list_append",{name(buffer),std::move(emitted)}));
  if(filtered){auto condition=statement(Stmt::If,invoke(1,item()));condition->body={append};loop->body.push_back(std::move(condition));}
  else loop->body.push_back(std::move(append));
  if(stateful){
    auto change=statement(Stmt::Assign,invoke(2,name(state)));change->name=state;
    auto condition=statement(Stmt::If,binary("<",binary("+",name(index),integer(1)),name(count)));
    condition->body={std::move(change)};loop->body.push_back(std::move(condition));
  }
  auto advance=statement(Stmt::Assign,binary("+",name(index),integer(1)));advance->name=index;
  loop->body.push_back(std::move(advance));fn.body.push_back(std::move(loop));
  fn.body.push_back(statement(Stmt::Return,call("$bytes_finish",{name(buffer)})));
  return lambda;
}
llvm::json::Value bytesBuildCapability(){
  return llvm::json::Object{{"source_name","bytes"},{"guide","docs/bytes-construction.md"},
    {"language",languageVersion},{"previously_reserved_name",true},{"source_version_changed",false},
    {"one_argument_conversion_preserved",true},
    {"forms",llvm::json::Array{"bytes(count,make)","bytes(values,transform)","bytes(values,predicate,transform)","bytes(count,initial,next,emit)"}},
    {"sequential",true},{"callback_effects","inferred union; ordinary caller/realm/task rules"},
    {"task_callbacks",true},{"source_errors",true},{"input_aliases_preserved",true},
    {"private_accumulator","list<i64> octets"},{"published_output_immutable",true},{"negative_count","E_ASSERT"},
    {"out_of_range_octet","E_RANGE"},
    {"state_advance_calls","max(0,count-1); emit precedes next"},
    {"construction_cost","one iteration per input/count, one private append per emitted octet and one final single-allocation conversion; O(iterations+octets), excluding callbacks/state/value construction"},
    {"linear_in_octets",true},
    {"new_native_runtime_symbol","nex_bytes_from_octets"},
    {"backends",llvm::json::Array{"reference","native","TypeScript"}},{"GPU_Wasm_constructor_support",false},
    {"new_worker_threads",false},{"new_authority",false},{"runtime_ABI_changed",false},
    {"extra_parallel_limits",false},{"limits","existing allocation, steps, deadlines and byte representation"}};
}
}
