"""Maintained source fixtures for native Windows acceptance (language 0.27)."""

CORE = r'''module windows_native;
trait Read {type Item; fn get(value:Self)->Read::Item<Self>;}
struct Box<T> {value:T;}
fn extract<T>(value:Box<T>)->T{return value.value;}
impl boxes<T>:Read for Box<T>{type Item=T;get=extract<T>;}
fn read<T:Read>(value:T)->Read::Item<T>{return Read<T>::get(value);}
fn main()->unit !{io}{
 let original:list<str>=["Я\u0000🧠","tail"];
 let changed:list<str>=push(original,"extra");
 assert(len(original)==2 && len(changed)==3 && len(original[0])==3);
 let captured:i64=read(Box<i64>(40));
 let add:fn(i64)->i64=fn(x:i64)->i64{return captured+x;};
 assert(add(2)==42);
 assert(unwrap(decode_json<Box<str>>(encode_json(Box<str>(original[0])))).value==original[0]);
 assert(unwrap(bytes([0,128,255]))==unwrap(bytes([0,128,255])));
 assert(false && 1/0==0 || true);
 assert(5e-324+0e0==5e-324);
 print(original[0]);print(add(2));
}
fn overflow_add()->unit{let x:i64=9223372036854775807+1;}
fn overflow_sub()->unit{let x:i64=-9223372036854775808-1;}
fn overflow_mul()->unit{let x:i64=9223372036854775807*2;}
fn overflow_div()->unit{let x:i64=-9223372036854775808/-1;}
fn divide_zero()->unit{let x:i64=1/0;}
fn bad_index()->unit{let x:list<str>=["owned"];let y:str=x[1];}
'''

TYPED_TASKS = r'''module windows_typed_tasks;
struct Failure {text:str;values:list<i64>;}
fn fail()->i64 !{task,throw}{task_yield();throw(Failure("Я\u0000🧠",[40,2]));}
fn main()->unit !{task,throw,io}{
 var finalized:bool=false;
 try{
  with_tasks(2,fn(scope:task_scope)->unit !{task,throw}{
   let child:task<i64>=task_spawn(scope,fail);task_wait(child);
  });
 }catch(e:Failure) if false {assert(false);}
 catch(e:Failure) if e.text=="Я\u0000🧠" {assert(e.values[0]+e.values[1]==42);print(e.text);}
 finally{task_yield();finalized=true;}
 assert(finalized);
 with_tasks(2,fn(scope:task_scope)->unit !{task,throw}{
  let queue:channel<i64>=channel_new<i64>(scope,1);
  let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();assert(task_send(queue,42));return 0;});
  assert(unwrap(task_recv(queue))==42);assert(task_wait(child)==0);task_close(queue);
 });
 print("finished");
}
fn cancel()->unit !{task,throw}{
 with_tasks(1,fn(scope:task_scope)->unit !{task,throw}{
  let queue:channel<i64>=channel_new<i64>(scope,0);
  let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{return unwrap(task_recv(queue));});
  assert(task_cancel(child));task_wait(child);
 });
}
fn deadline()->unit !{task}{while true{task_yield();}}
'''

FILES = r'''module windows_files;
server fn main()->unit !{fs,io}{
 let text:str="Я\u0000🧠";
 assert(unwrap(file_write_text("nested/данные.txt",text)));
 assert(unwrap(file_read_text("nested/данные.txt"))==text);
 let data:bytes=unwrap(bytes([65,0,255,66]));
 assert(unwrap(file_write_bytes("binary",data)));
 assert(unwrap(file_read_bytes("binary"))==data);
 assert(error_code(file_read_text("binary"))=="E_UTF8");
 assert(error_code(file_read_text("../escape"))=="VALIDATION");
 let f:file=unwrap(file_open_write("stream"));let alias:file=f;
 assert(unwrap(file_write(f,data))==4);assert(unwrap(file_flush(f)));
 assert(file_close(f) && !file_is_open(alias) && !file_close(alias));
 let g:file=unwrap(file_open_append("stream"));assert(unwrap(file_seek(g,0))==0);
 assert(unwrap(file_write(g,utf8_bytes("Z")))==1);file_close(g);
 let h:file=unwrap(file_open_read("stream"));
 assert(unwrap(file_read(h,5))==data+utf8_bytes("Z"));file_close(h);
 print(text);
}
server fn denied()->unit !{fs}{assert(error_code(file_write_text("denied","x"))=="CAPABILITY");}
'''

TASK_FILES = r'''module windows_task_files;
struct FileFailure {handle:file;}
server fn main()->unit !{task,throw,fs,io}{
 let data:bytes=unwrap(bytes([0,255,65]));
 with_tasks(2,server fn(scope:task_scope)->unit !{task,throw,fs}{
  let future:task<file>=task_spawn(scope,server fn()->file !{task,fs}{
   let f:file=unwrap(file_open_write("task-stream"));assert(unwrap(file_write(f,data))==3);task_yield();return f;
  });
  let f:file=task_wait(future);assert(unwrap(file_size(f))==3);file_close(f);
  assert(unwrap(file_write_text("task-text","Я\u0000🧠")));
  assert(unwrap(file_read_text("task-text"))=="Я\u0000🧠");
 });
 print("task-files-ok");
}
server fn typed()->unit !{task,throw,fs,io}{
 try{
  with_tasks(2,server fn(scope:task_scope)->unit !{task,throw,fs}{
   let future:task<i64>=task_spawn(scope,server fn()->i64 !{task,throw,fs}{
    let f:file=unwrap(file_open_write("typed-owned"));assert(unwrap(file_write(f,utf8_bytes("kept")))==4);throw(FileFailure(f));
   });task_wait(future);
  });
 }catch(error:FileFailure){assert(file_is_open(error.handle));assert(unwrap(file_size(error.handle))==4);file_close(error.handle);}
 finally{task_yield();}
 print("typed-file-ok");
}
server fn cancelled()->unit !{task,throw,fs}{
 with_tasks(1,server fn(scope:task_scope)->unit !{task,throw,fs}{
  let ready:channel<i64>=channel_new<i64>(scope,1);let parked:channel<i64>=channel_new<i64>(scope,0);
  let child:task<i64>=task_spawn(scope,server fn()->i64 !{task,fs}{
   let f:file=unwrap(file_open_write("cancel-owned"));assert(unwrap(file_write(f,utf8_bytes("owned")))==5);
   assert(task_send(ready,1));try{return unwrap(task_recv(parked));}finally{file_write_text("cancel-finally","bad");}
  });assert(unwrap(task_recv(ready))==1);assert(task_cancel(child));task_wait(child);
 });
}
'''

REJECTED = [
    ('overflow_literal', 'module bad;fn main()->i64{return 9223372036854775808;}', 'E_RANGE'),
    ('missing_effect', 'module bad;fn main()->unit{print(1);}', 'E_EFFECT'),
    ('wrong_realm', 'module bad;client fn main()->result<str>!{io}{return read_env("x");}', 'E_REALM'),
]
