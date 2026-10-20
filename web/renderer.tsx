import { createElement } from 'react';
import type { ReactNode, SyntheticEvent, MouseEvent } from 'react';
import type { View, Event } from './program.ts';
import { makeEvent } from './program.ts';
import { NexError } from './nex-runtime.ts';
import { safeViewURL, sameApplicationOrigin } from './urls.ts';

const tags = new Set(['main', 'header', 'footer', 'section', 'article', 'aside', 'nav', 'div', 'span', 'p',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'button', 'form', 'label', 'input',
  'textarea', 'select', 'option', 'fieldset', 'legend', 'strong', 'em', 'small', 'pre', 'code',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'caption', 'details', 'summary', 'hr', 'br', 'img']);
const attributes = new Set(['id', 'class', 'title', 'role', 'lang', 'dir', 'href', 'src', 'alt', 'target', 'rel',
  'type', 'name', 'value', 'placeholder', 'for', 'checked', 'disabled', 'required', 'readonly', 'multiple',
  'min', 'max', 'step', 'maxlength', 'tabindex', 'autocomplete', 'rows', 'cols', 'key']);
const aliases: Record<string, string> = { class: 'className', for: 'htmlFor', readonly: 'readOnly',
  maxlength: 'maxLength', tabindex: 'tabIndex', autocomplete: 'autoComplete' };
const booleans = new Set(['checked', 'disabled', 'required', 'readonly', 'multiple']);
const numbers = new Set(['maxlength', 'tabindex', 'rows', 'cols']);
const handlers = new Map([['click', 'onClick'], ['input', 'onChange'], ['change', 'onChange'], ['submit', 'onSubmit'], ['navigate', 'onClick']]);
const voidTags = new Set(['input', 'img', 'hr', 'br']);
function invalid(message: string): never { throw new NexError('E_UI', message); }
function inputValue(target: EventTarget | null): string {
  if (target instanceof HTMLInputElement) return target.type === 'checkbox' || target.type === 'radio' ? String(target.checked) : target.value;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return target.value;
  return '';
}
export function currentPath(): string { return location.pathname + location.search + location.hash; }
export function renderView(root: View, dispatch: (event: Event) => void): ReactNode {
  let visited = 0;
  function render(view: View, depth: number, fallbackKey: number): ReactNode {
    if (++visited > 10000 || depth > 256) throw new NexError('E_UI_LIMIT', 'View exceeds node/depth limit');
    if (view.tag === 'text') {
      if (view.attributes.length || view.events.length || view.children.length) invalid('Text view cannot have attributes/events/children');
      return view.text;
    }
    if (!tags.has(view.tag)) invalid('Unsupported element: ' + view.tag);
    if (view.text !== '') invalid('Element text must be represented by text children');
    if (voidTags.has(view.tag) && view.children.length) invalid('Void element cannot have children');
    const props: Record<string, unknown> = { key: fallbackKey };
    const seen = new Set<string>();
    for (const attribute of view.attributes) {
      const { name, value } = attribute;
      if (!attributes.has(name) && !/^(aria|data)-[a-z][a-z0-9-]*$/.test(name)) invalid('Unsupported attribute: ' + name);
      if (seen.has(name)) invalid('Duplicate attribute: ' + name); seen.add(name);
      const key = aliases[name] ?? name;
      if (booleans.has(name)) {
        if (value !== 'true' && value !== 'false') invalid('Boolean attribute requires true/false: ' + name);
        props[key] = value === 'true';
      } else if (numbers.has(name)) {
        if (!/^-?[0-9]+$/.test(value) || !Number.isSafeInteger(Number(value))) invalid('Invalid integer attribute: ' + name);
        props[key] = Number(value);
      } else props[key] = name === 'href' || name === 'src' ? safeViewURL(value, name, new URL(globalThis.location?.href ?? 'http://localhost/')) : value;
    }
    if (props.target === '_blank') props.rel = 'noopener noreferrer';
    const bound = new Set<string>();
    for (const binding of view.events) {
      const handler = handlers.get(binding.event);
      if (!handler) invalid('Unsupported event: ' + binding.event);
      if (bound.has(handler)) invalid('Duplicate event handler: ' + binding.event); bound.add(handler);
      props[handler] = (event: SyntheticEvent<HTMLElement>) => {
        if (binding.event === 'navigate') {
          const click = event as MouseEvent<HTMLElement>;
          if (click.button !== 0 || click.metaKey || click.ctrlKey || click.shiftKey || click.altKey) return;
          const href = typeof props.href === 'string' ? props.href : invalid('Navigation requires href');
          const url = new URL(href, location.href);
          if (!sameApplicationOrigin(url, new URL(location.href)) || (props.target && props.target !== '_self')) return;
          event.preventDefault(); history.pushState(null, '', url.pathname + url.search + url.hash);
        } else if (binding.event === 'submit') event.preventDefault();
        dispatch(makeEvent(binding.action, inputValue(event.currentTarget), currentPath()));
      };
    }
    if ((view.tag === 'input' || view.tag === 'textarea') && !bound.has('onChange') && (seen.has('value') || seen.has('checked'))) props.readOnly = true;
    const children = view.children.map((child, index) => render(child, depth + 1, index));
    return voidTags.has(view.tag) ? createElement(view.tag, props) : createElement(view.tag, props, children);
  }
  return render(root, 0, 0);
}
