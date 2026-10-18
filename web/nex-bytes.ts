// Internal binary-value primitive; source-language integration is separate.
const Octets = Uint8Array;
const owned = Symbol('nex owned bytes');
const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const decodeTable = new Int16Array(128).fill(-1);
for (let i=0;i<alphabet.length;++i) decodeTable[alphabet.charCodeAt(i)]=i;

export class ByteError extends Error {
  readonly code: string;
  constructor(code: string, message: string) { super(message); this.code=code; }
}
function fail(code: string, message: string): never { throw new ByteError(code,message); }
function sizeAllowed(size: number): number {
  if (!Number.isSafeInteger(size)||size<0) fail('E_LIMIT','byte buffer exceeds supported size');
  return size;
}
function byte(value: bigint): number {
  if (typeof value!=='bigint'||value<0n||value>255n) fail('E_RANGE','byte value must be between 0 and 255');
  return Number(value);
}

export class ByteBuffer {
  readonly #storage: Uint8Array;
  readonly #offset: number;
  readonly #count: number;
  private constructor(key: symbol, storage: Uint8Array, offset: number, count: number) {
    if (key!==owned) throw new TypeError('Use ByteBuffer.copy or a checked constructor');
    this.#storage=storage;this.#offset=offset;this.#count=count;Object.freeze(this);
  }
  static empty(): ByteBuffer { return new ByteBuffer(owned,new Octets(0),0,0); }
  static copy(values: ArrayLike<number>): ByteBuffer {
    const count=sizeAllowed(values.length), storage=new Octets(count);
    for (let i=0;i<count;++i) {
      const value=values[i];
      if (!Number.isInteger(value)||value<0||value>255) fail('E_RANGE','byte value must be between 0 and 255');
      storage[i]=value;
    }
    return new ByteBuffer(owned,storage,0,count);
  }
  static fromIntegers(values: ArrayLike<bigint>): ByteBuffer {
    const count=sizeAllowed(values.length), storage=new Octets(count);
    for (let i=0;i<count;++i) storage[i]=byte(values[i]);
    return new ByteBuffer(owned,storage,0,count);
  }
  get length(): bigint { return BigInt(this.#count); }
  #index(position: bigint): number {
    if (position<0n||position>=BigInt(this.#count)) fail('E_BOUNDS','byte index is outside buffer bounds');
    return Number(position);
  }
  at(position: bigint): bigint { return BigInt(this.#storage[this.#offset+this.#index(position)]); }
  #copy(): Uint8Array {
    const result=new Octets(this.#count);
    for (let i=0;i<this.#count;++i) result[i]=this.#storage[this.#offset+i];
    return result;
  }
  toUint8Array(): Uint8Array { return this.#copy(); }
  slice(start: bigint, length: bigint): ByteBuffer {
    const count=BigInt(this.#count);
    if (start<0n||length<0n||start>count||length>count-start) fail('E_BOUNDS','slice is outside byte buffer bounds');
    if (!length) return ByteBuffer.empty();
    return new ByteBuffer(owned,this.#storage,this.#offset+Number(start),Number(length));
  }
  set(position: bigint, value: bigint): ByteBuffer {
    const selected=this.#index(position), replacement=byte(value);
    if (this.#storage[this.#offset+selected]===replacement) return this;
    const storage=this.#copy();storage[selected]=replacement;
    return new ByteBuffer(owned,storage,0,this.#count);
  }
  append(value: bigint): ByteBuffer {
    const replacement=byte(value), count=sizeAllowed(this.#count+1), storage=new Octets(count);
    for (let i=0;i<this.#count;++i) storage[i]=this.#storage[this.#offset+i];
    storage[this.#count]=replacement;return new ByteBuffer(owned,storage,0,count);
  }
  concat(other: ByteBuffer): ByteBuffer {
    const count=sizeAllowed(this.#count+other.#count);
    if (!this.#count) return other;if (!other.#count) return this;
    const storage=new Octets(count);
    for (let i=0;i<this.#count;++i) storage[i]=this.#storage[this.#offset+i];
    for (let i=0;i<other.#count;++i) storage[this.#count+i]=other.#storage[other.#offset+i];
    return new ByteBuffer(owned,storage,0,count);
  }
  equals(other: ByteBuffer): boolean {
    if (this.#count!==other.#count) return false;
    if (this.#storage===other.#storage&&this.#offset===other.#offset) return true;
    for (let i=0;i<this.#count;++i) if (this.#storage[this.#offset+i]!==other.#storage[other.#offset+i]) return false;
    return true;
  }
  base64(): string {
    let result='';
    for (let i=0;i<this.#count;i+=3) {
      const a=this.#storage[this.#offset+i], b=i+1<this.#count?this.#storage[this.#offset+i+1]:0,
        c=i+2<this.#count?this.#storage[this.#offset+i+2]:0;
      result+=alphabet[a>>2]+alphabet[((a&3)<<4)|(b>>4)];
      result+=i+1<this.#count?alphabet[((b&15)<<2)|(c>>6)]:'=';
      result+=i+2<this.#count?alphabet[c&63]:'=';
    }
    return result;
  }
  static fromBase64(text: string): ByteBuffer {
    const invalid=(): never=>fail('E_BASE64','invalid canonical base64');
    if (text.length%4) invalid();if (!text.length) return ByteBuffer.empty();
    const decode=(index: number): number=>{
      const code=text.charCodeAt(index), value=code<128?decodeTable[code]:-1;
      if (value<0) invalid();return value;
    };
    const padding=Number(text.endsWith('='))+Number(text[text.length-2]==='='),
      count=sizeAllowed(text.length/4*3-padding), storage=new Octets(count);
    let offset=0;
    for (let i=0;i<text.length;i+=4) {
      const a=decode(i), b=decode(i+1), c=text[i+2], d=text[i+3], last=i+4===text.length;
      if (c==='=') {
        if (!last||d!=='='||(b&15)!==0) invalid();storage[offset++]=(a<<2)|(b>>4);continue;
      }
      const cv=decode(i+2);storage[offset++]=(a<<2)|(b>>4);
      if (d==='=') {
        if (!last||(cv&3)!==0) invalid();storage[offset++]=(b<<4)|(cv>>2);continue;
      }
      const dv=decode(i+3);storage[offset++]=(b<<4)|(cv>>2);storage[offset++]=(cv<<6)|dv;
    }
    return new ByteBuffer(owned,storage,0,count);
  }
}
Object.freeze(ByteBuffer.prototype);
Object.freeze(ByteBuffer);
