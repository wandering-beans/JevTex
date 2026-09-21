export function createI18n(catalogs, preferred = 'ja') {
  let language = Object.hasOwn(catalogs, preferred) ? preferred : 'ja';
  const interpolate = (text, params) => text.replace(/\{(\w+)\}/g, (match, key) => params[key] ?? match);
  // Compatibility with existing saved results and the server's Japanese messages.
  const serverPatterns = Object.entries(catalogs.ja.messages).filter(([key]) => key.startsWith('server.')).map(([key, text]) => {
    const names = [];
    const pattern = text.split(/(\{\w+\})/).map(part => {
      if (/^\{\w+\}$/.test(part)) { names.push(part.slice(1,-1)); return '(.+?)'; }
      return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }).join('');
    return {key, names, pattern:new RegExp('^'+pattern+'$', 's')};
  });
  return {
    get language() { return language; },
    setLanguage(value) { language = Object.hasOwn(catalogs, value) ? value : 'ja'; },
    t(key, params = {}) { return interpolate(catalogs[language].messages[key] ?? catalogs.ja.messages[key] ?? key, params); },
    serverMessage(message) {
      for (const {key, names, pattern} of serverPatterns) {
        const match = pattern.exec(message);
        if (match) return this.t(key, Object.fromEntries(names.map((name,i) => [name,match[i+1]])));
      }
      return message;
    },
    apply(root) {
      for (const attribute of ['text','placeholder','aria-label']) {
        const name = attribute === 'text' ? 'data-i18n' : 'data-i18n-'+attribute;
        root.querySelectorAll(`[${name}]`).forEach(node => {
          const value = this.t(node.getAttribute(name));
          if (attribute === 'text') node.textContent = value;
          else node.setAttribute(attribute, value);
        });
      }
    }
  };
}
