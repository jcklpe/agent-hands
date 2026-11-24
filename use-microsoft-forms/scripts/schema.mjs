import {createHash} from 'node:crypto';

export function fail(code, message) { throw Object.assign(new Error(message), {code}); }
function keys(value, allowed, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key => !allowed.includes(key))) fail('invalid_spec', `${label} contains an unsupported field or is not an object.`);
}
function text(value, max, label, blank = false) {
  if (typeof value !== 'string' || value.length > max || (!blank && !value.trim()) || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) fail('invalid_spec', `${label} must be ${blank ? 'a' : 'nonempty'} text of at most ${max} characters without control characters.`);
  return value;
}
export function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
export const digest = value => createHash('sha256').update(canonical(value)).digest('hex');
export function validateSpec(input) {
  keys(input, ['version','title','description','acceptResponses','questions'], 'Form');
  if (input.version !== 1 || input.acceptResponses !== false) fail('invalid_spec', 'Use version 1 and acceptResponses false. This command creates closed drafts only.');
  text(input.title, 90, 'Title'); text(input.description, 1000, 'Description', true);
  if (!Array.isArray(input.questions) || !input.questions.length || input.questions.length > 200) fail('invalid_spec', 'Provide 1 to 200 questions.');
  const seen = new Set();
  for (const q of input.questions) {
    keys(q, ['id','title','description','type','required','longAnswer','multiple','options','branches','next'], 'Question');
    if (typeof q.id !== 'string' || !/^[a-z][a-z0-9_-]{0,39}$/.test(q.id) || seen.has(q.id) || q.id === 'end') fail('invalid_spec', 'Question IDs must be unique lowercase identifiers, up to 40 characters; end is reserved.');
    seen.add(q.id); text(q.title, 1000, `Question ${q.id} title`);
    if (q.description !== undefined) text(q.description, 1000, `Question ${q.id} description`, true);
    if (!['text','choice','date'].includes(q.type) || typeof q.required !== 'boolean') fail('invalid_spec', `Question ${q.id} needs a supported type and an explicit required boolean.`);
    if (q.type === 'choice') {
      if (!Array.isArray(q.options) || q.options.length < 2 || q.options.length > 60 || new Set(q.options).size !== q.options.length) fail('invalid_spec', `Question ${q.id} requires 2 to 60 distinct options.`);
      q.options.forEach(v => text(v, 1000, `Question ${q.id} option`));
      if (q.multiple !== undefined && typeof q.multiple !== 'boolean') fail('invalid_spec', 'multiple must be boolean.');
      if (q.longAnswer !== undefined) fail('invalid_spec', 'Only text questions support longAnswer.');
    } else if (q.options !== undefined || q.multiple !== undefined || q.branches !== undefined) fail('invalid_spec', 'Only choice questions support options, multiple and branches.');
    if (q.longAnswer !== undefined && (q.type !== 'text' || typeof q.longAnswer !== 'boolean')) fail('invalid_spec', 'Only text questions support a boolean longAnswer.');
    if (q.branches !== undefined) {
      if (q.multiple || !q.branches || typeof q.branches !== 'object' || Array.isArray(q.branches) || Object.keys(q.branches).some(k => !q.options.includes(k))) fail('invalid_spec', 'Branches require a single-choice question and exact option labels.');
    }
    if(q.next!==undefined&&(q.type!=='choice'||q.multiple))fail('invalid_spec','This initial editor supports single-choice answer branching only.');
  }
  const positions = new Map(input.questions.map((q, i) => [q.id, i]));
  input.questions.forEach((q, i) => {
    const targets = [...Object.values(q.branches || {}), ...(q.next !== undefined ? [q.next] : [])];
    for (const target of targets) if (target !== 'end' && (!positions.has(target) || positions.get(target) <= i)) fail('invalid_branch', `Question ${q.id} must branch forward to an existing question or end.`);
  });
  return structuredClone(input);
}
export function reachableQuestions(spec) {
  validateSpec(spec);
  const found = new Set(), todo = [spec.questions[0].id];
  const byId = new Map(spec.questions.map((q,i) => [q.id,{q,i}]));
  while (todo.length) {
    const id=todo.pop(); if (id === 'end' || found.has(id)) continue;
    found.add(id); const {q,i}=byId.get(id);
    const next=q.next ?? spec.questions[i+1]?.id ?? 'end';
    if (q.type === 'choice') q.options.forEach(option => todo.push(q.branches?.[option] ?? next));
    else todo.push(next);
  }
  return spec.questions.filter(q => found.has(q.id)).map(q => q.id);
}
