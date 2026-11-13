import { NexError } from './nex-runtime.ts';

function localMobileOrigin(url: URL): boolean {
  return url.protocol === 'capacitor:' && url.hostname === 'localhost' &&
    url.port === '' && url.username === '' && url.password === '';
}
function localDesktopOrigin(url: URL): boolean {
  return url.protocol === 'nex:' && url.hostname === 'app' &&
    url.port === '' && url.username === '' && url.password === '';
}

// URL.origin is "null" for custom schemes. Two such strings do not prove
// same origin: mailto, file, data and an unrelated mobile host must stay distinct.
export function sameApplicationOrigin(url: URL, base: URL): boolean {
  if (base.origin !== 'null') return url.origin === base.origin;
  return (localMobileOrigin(base) && localMobileOrigin(url)) ||
    (localDesktopOrigin(base) && localDesktopOrigin(url));
}

export function safeViewURL(value: string, attribute: string, base: URL): string {
  function invalid(message: string): never { throw new NexError('E_UI', message); }
  if (value.trim() !== value || /[\u0000-\u001f\u007f]/.test(value)) invalid('URL contains whitespace/control characters');
  let url: URL;
  try { url = new URL(value, base); }
  catch { return invalid('Invalid URL'); }
  const protocols = attribute === 'href' ? ['http:', 'https:', 'mailto:', 'tel:'] : ['http:', 'https:'];
  if (protocols.includes(url.protocol)) return value;
  // The local iOS host needs relative asset/navigation paths. This never admits
  // explicit capacitor URLs, authority-relative URLs or custom remote hosts.
  const relative = !/^[a-z][a-z0-9+.-]*:/i.test(value) && !value.startsWith('//') && !value.includes('\\');
  if (relative && (localMobileOrigin(base) || localDesktopOrigin(base)) && sameApplicationOrigin(url, base)) return value;
  return invalid('Unsupported URL protocol');
}
