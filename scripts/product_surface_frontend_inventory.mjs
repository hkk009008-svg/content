#!/usr/bin/env node
/** Static frontend transport facts from the TypeScript compiler AST. */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";
const require = createRequire(new URL("../web/package.json", import.meta.url));
let ts;
try {
  ts = require("typescript");
  const locked = require("./package-lock.json").packages?.["node_modules/typescript"]?.version;
  if (!locked || ts.version !== locked) {
    throw new Error(`installed ${ts.version} does not match package-lock ${locked || "missing"}`);
  }
} catch (error) {
  process.stderr.write(`TypeScript compiler unavailable: ${error.message}\n`);
  process.exit(2);
}
const METHODS = new Set(["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]);
const EXCLUDED = new Set(["__tests__", "dist", "node_modules", "test", "tests"]);
const COMPARISONS = new Set([
  "EqualsEqualsToken", "EqualsEqualsEqualsToken", "ExclamationEqualsToken",
  "ExclamationEqualsEqualsToken", "LessThanToken", "LessThanEqualsToken",
  "GreaterThanToken", "GreaterThanEqualsToken",
].map((name) => ts.SyntaxKind[name]));
function die(message, code = 2) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}
function rootArgument(argv) {
  if (argv.length !== 2 || argv[0] !== "--root") {
    die("usage: product_surface_frontend_inventory.mjs --root <repo-root>");
  }
  return path.resolve(argv[1]);
}
function frontendFiles(root) {
  const base = path.join(root, "web", "src");
  if (!fs.existsSync(base)) return [];
  const found = [];
  function visit(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (entry.isDirectory() && EXCLUDED.has(entry.name)) continue;
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(absolute);
      else if (entry.isFile() && /\.(?:ts|tsx)$/.test(entry.name) &&
               !/\.(?:spec|test)\.(?:ts|tsx)$/.test(entry.name)) found.push(absolute);
    }
  }
  visit(base);
  return found.sort();
}
function relative(root, fileName) {
  return path.relative(root, fileName).split(path.sep).join("/");
}
function source(root, file, node) {
  const point = file.getLineAndCharacterOfPosition(node.getStart(file));
  return { path: relative(root, file.fileName), line: point.line + 1 };
}
function text(file, node) {
  return node ? node.getText(file).replace(/\s+/g, " ").trim() : "";
}
function unwrap(node) {
  let value = node;
  while (value && (
    ts.isParenthesizedExpression(value) || ts.isAsExpression(value) ||
    ts.isTypeAssertionExpression(value) || ts.isNonNullExpression(value) ||
    ts.isSatisfiesExpression(value)
  )) value = value.expression;
  return value;
}
function symbol(checker, node) {
  const value = unwrap(node);
  return value && ts.isIdentifier(value) ? checker.getSymbolAtLocation(value) : undefined;
}
function isGlobal(checker, node, name) {
  const value = unwrap(node);
  if (!value || !ts.isIdentifier(value) || value.text !== name) return false;
  const found = checker.getSymbolAtLocation(value);
  if (!found || found.flags & ts.SymbolFlags.Alias) return false;
  const declarations = found.getDeclarations() || [];
  return declarations.length > 0 && declarations.every((declaration) => {
    const owner = declaration.getSourceFile();
    return owner.isDeclarationFile && /^lib\..*\.d\.ts$/.test(path.basename(owner.fileName));
  });
}
function propertyName(node) {
  const value = unwrap(node);
  if (value && ts.isPropertyAccessExpression(value)) return value.name.text;
  if (value && ts.isElementAccessExpression(value) && value.argumentExpression &&
      ts.isStringLiteralLike(value.argumentExpression)) return value.argumentExpression.text;
  return undefined;
}
function declaredName(node) {
  if (!node) return undefined;
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) {
    return node.text;
  }
  return undefined;
}
function literal(checker, constants, node) {
  const value = unwrap(node);
  if (!value) return undefined;
  if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) return value.text;
  if (ts.isIdentifier(value)) return constants.get(checker.getSymbolAtLocation(value));
  return undefined;
}
function resolveUrl(checker, constants, node) {
  const value = unwrap(node);
  const fixed = literal(checker, constants, value);
  if (fixed !== undefined) return fixed;
  if (!value || !ts.isTemplateExpression(value)) return null;
  let result = value.head.text;
  let index = 0;
  for (const span of value.templateSpans) {
    const replacement = literal(checker, constants, span.expression);
    result += replacement === undefined ? `{${++index}}` : replacement;
    result += span.literal.text;
  }
  return result;
}
function fetchMethod(checker, constants, call) {
  if (call.arguments.length < 2) return ["GET", null];
  const options = unwrap(call.arguments[1]);
  if (isGlobal(checker, options, "undefined")) return ["GET", null];
  if (!ts.isObjectLiteralExpression(options)) {
    return [null, "fetch options is not an inline object literal"];
  }
  let value = "GET";
  let certain = true;
  for (const item of options.properties) {
    if (ts.isSpreadAssignment(item) || item.name && ts.isComputedPropertyName(item.name)) {
      certain = false; continue;
    }
    if (!item.name || declaredName(item.name) !== "method") continue;
    if (ts.isPropertyAssignment(item)) {
      const found = literal(checker, constants, item.initializer)?.toUpperCase();
      value = found && METHODS.has(found) ? found : null;
      certain = value !== null;
    } else if (ts.isShorthandPropertyAssignment(item)) {
      const found = literal(checker, constants, item.name)?.toUpperCase();
      value = found && METHODS.has(found) ? found : null;
      certain = value !== null;
    } else {
      certain = false;
    }
  }
  return certain ? [value, null] : [null, "fetch method is not a static HTTP method"];
}
function functionLike(node) {
  return ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) ||
    ts.isArrowFunction(node) || ts.isMethodDeclaration(node);
}
function callback(initializer) {
  const value = unwrap(initializer);
  if (value && (ts.isArrowFunction(value) || ts.isFunctionExpression(value))) return value;
  if (value && ts.isCallExpression(value) &&
      ts.isIdentifier(unwrap(value.expression)) &&
      unwrap(value.expression).text === "useCallback") {
    const first = unwrap(value.arguments[0]);
    if (first && (ts.isArrowFunction(first) || ts.isFunctionExpression(first))) return first;
  }
  return undefined;
}
function functionFacts(checker, file) {
  const byNode = new Map();
  const candidates = [];
  function add(node, name, nameNode, candidate) {
    if (byNode.has(node)) return;
    const parameters = node.parameters
      .filter((parameter) => ts.isIdentifier(parameter.name))
      .map((parameter) => checker.getSymbolAtLocation(parameter.name))
      .filter(Boolean);
    const info = { node, name, parameters, candidate,
      symbol: nameNode ? checker.getSymbolAtLocation(nameNode) : undefined };
    byNode.set(node, info);
    if (candidate && name && info.symbol) candidates.push(info);
  }
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name) add(node, node.name.text, node.name, true);
    else if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const found = callback(node.initializer);
      if (found) add(found, node.name.text, node.name, true);
    } else if (ts.isMethodDeclaration(node)) add(node, declaredName(node.name), node.name, false);
    else if (functionLike(node)) add(node, undefined, undefined, false);
    ts.forEachChild(node, visit);
  }
  visit(file);
  return { byNode, candidates };
}
function nearestFunction(node, functions) {
  let parent = node.parent;
  while (parent) {
    if (functionLike(parent)) return functions.byNode.get(parent);
    parent = parent.parent;
  }
  return undefined;
}
function ownerName(node, functions) {
  let parent = node.parent;
  while (parent) {
    if (functionLike(parent)) {
      const info = functions.byNode.get(parent);
      if (info?.name) return info.name;
    }
    parent = parent.parent;
  }
  return undefined;
}
function responseBinding(checker, call) {
  let value = call;
  while (value.parent && (
    ts.isAwaitExpression(value.parent) || ts.isParenthesizedExpression(value.parent) ||
    ts.isAsExpression(value.parent) || ts.isNonNullExpression(value.parent)
  )) value = value.parent;
  let name;
  if (ts.isVariableDeclaration(value.parent)) name = value.parent.name;
  else if (ts.isBinaryExpression(value.parent) &&
           value.parent.operatorToken.kind === ts.SyntaxKind.EqualsToken) {
    name = value.parent.left;
  }
  return name && ts.isIdentifier(unwrap(name))
    ? checker.getSymbolAtLocation(unwrap(name))
    : undefined;
}
function boundProperty(checker, node, binding, name) {
  const value = unwrap(node);
  return Boolean(value && ts.isPropertyAccessExpression(value) &&
    value.name.text === name && symbol(checker, value.expression) === binding);
}
function scanAfter(container, call, inspect) {
  function visit(node) {
    if (node !== container && functionLike(node)) return;
    if (node.getStart() > call.end) inspect(node);
    ts.forEachChild(node, visit);
  }
  visit(container || call.getSourceFile());
}
function observation(checker, call, container, kind) {
  const binding = responseBinding(checker, call);
  if (!binding) return "unknown";
  let observed = false;
  scanAfter(container, call, (node) => {
    if (observed) return;
    if (kind === "fetch") {
      if (boundProperty(checker, node, binding, "ok")) observed = true;
      if (ts.isBinaryExpression(node) && COMPARISONS.has(node.operatorToken.kind)) {
        const left = boundProperty(checker, node.left, binding, "status");
        const right = boundProperty(checker, node.right, binding, "status");
        const numeric = (candidate) => {
          const value = unwrap(candidate);
          const number = value && ts.isNumericLiteral(value) ? Number(value.text) : NaN;
          return Number.isInteger(number) && number >= 100 && number <= 599;
        };
        if (left && numeric(node.right) || right && numeric(node.left)) observed = true;
      }
    } else {
      if (boundProperty(checker, node, binding, "onerror")) observed = true;
      const expression = ts.isCallExpression(node) ? unwrap(node.expression) : undefined;
      if (expression && ts.isPropertyAccessExpression(expression) &&
          expression.name.text === "addEventListener" &&
          symbol(checker, expression.expression) === binding &&
          literal(checker, new Map(), node.arguments[0]) === "error") observed = true;
    }
  });
  return observed ? "observed" : "not_observed";
}
function moduleFacts(checker, file) {
  const constants = new Map();
  const imports = new Map();
  for (const statement of file.statements) {
    if (ts.isVariableStatement(statement) && statement.declarationList.flags & ts.NodeFlags.Const) {
      for (const item of statement.declarationList.declarations) {
        if (!ts.isIdentifier(item.name) || !item.initializer) continue;
        const value = unwrap(item.initializer);
        if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) {
          constants.set(checker.getSymbolAtLocation(item.name), value.text);
        }
      }
    }
    if (!ts.isImportDeclaration(statement) || !statement.importClause) continue;
    const clause = statement.importClause;
    const names = [];
    if (clause.name) names.push(clause.name);
    if (clause.namedBindings) {
      if (ts.isNamespaceImport(clause.namedBindings)) names.push(clause.namedBindings.name);
      else names.push(...clause.namedBindings.elements.map((item) => item.name));
    }
    for (const name of names) imports.set(checker.getSymbolAtLocation(name), name.text);
  }
  return { constants, imports };
}
function unknown(root, file, node, kind, reason, expression, owner) {
  const row = { domain: "frontend", kind, reason,
    expression: expression.replace(/\s+/g, " ").trim(),
    source: source(root, file, node) };
  if (owner) row.owner = owner;
  return row;
}
function transportTarget(checker, expression, aliases, callKind) {
  const value = unwrap(expression);
  if (value && ts.isIdentifier(value)) {
    const found = checker.getSymbolAtLocation(value);
    if (value.text === "fetch" && !isGlobal(checker, value, "fetch")) {
      return { kind: "fetch", shadowed: true };
    }
    if (value.text === "EventSource" && !isGlobal(checker, value, "EventSource")) {
      return { kind: "event_source", shadowed: true };
    }
    if (aliases.has(found)) return { kind: aliases.get(found), alias: value.text };
    if (callKind === "call" && isGlobal(checker, value, "EventSource")) {
      return { kind: "event_source", shadowed: true };
    }
  }
  const member = propertyName(value);
  if (member === "fetch" || member === "EventSource") {
    return { kind: member === "fetch" ? "fetch" : "event_source", shadowed: true };
  }
  return undefined;
}
function analyzeFile(root, file, checker) {
  const { constants, imports } = moduleFacts(checker, file);
  const functions = functionFacts(checker, file);
  const aliases = new Map();
  const unresolved = [];
  function collectAliases(node) {
    if (ts.isVariableDeclaration(node) && node.initializer && ts.isIdentifier(node.name)) {
      const value = unwrap(node.initializer);
      let kind;
      if (isGlobal(checker, value, "fetch") || propertyName(value) === "fetch") kind = "fetch";
      else if (isGlobal(checker, value, "EventSource") || propertyName(value) === "EventSource") {
        kind = "event_source";
      } else if (ts.isIdentifier(value)) kind = aliases.get(checker.getSymbolAtLocation(value));
      if (kind) {
        aliases.set(checker.getSymbolAtLocation(node.name), kind);
        unresolved.push(unknown(
          root, file, node, "aliased_transport", "aliased transports are not expanded",
          text(file, node), node.name.text,
        ));
      }
    } else if (ts.isVariableDeclaration(node) && ts.isObjectBindingPattern(node.name)) {
      for (const item of node.name.elements) {
        const property = declaredName(item.propertyName || item.name);
        if ((property === "fetch" || property === "EventSource") && ts.isIdentifier(item.name)) {
          aliases.set(
            checker.getSymbolAtLocation(item.name),
            property === "fetch" ? "fetch" : "event_source",
          );
          unresolved.push(unknown(
            root, file, item, "aliased_transport", "aliased transports are not expanded",
            text(file, item), item.name.text,
          ));
        }
      }
    }
    ts.forEachChild(node, collectAliases);
  }
  collectAliases(file);
  const transports = [];
  const operations = [];
  const suspiciousNodes = new Set();
  function collect(node) {
    if (ts.isCallExpression(node) || ts.isNewExpression(node)) {
      const fetchGlobal = ts.isCallExpression(node) && isGlobal(checker, node.expression, "fetch");
      const eventGlobal = ts.isNewExpression(node) && isGlobal(checker, node.expression, "EventSource");
      if (fetchGlobal || eventGlobal) {
        const kind = fetchGlobal ? "fetch" : "event_source";
        const urlNode = node.arguments?.[0];
        const urlTemplate = resolveUrl(checker, constants, urlNode);
        const owner = ownerName(node, functions);
        const container = nearestFunction(node, functions);
        const [method, methodReason] = kind === "fetch"
          ? fetchMethod(checker, constants, node)
          : ["GET", null];
        const ref = `${relative(root, file.fileName)}:${node.getStart(file)}`;
        const row = {
          _transport_ref: ref,
          kind,
          method,
          non_2xx_observation: kind === "fetch"
            ? observation(checker, node, container?.node, kind)
            : null,
          non_2xx_observation_applicability: kind === "fetch" ? "applicable" : "not_applicable",
          source: source(root, file, node),
          url_expression: text(file, urlNode),
          url_template: urlTemplate,
        };
        if (owner) row.enclosing_function = owner;
        if (kind === "event_source") {
          row.transport_error_observation = observation(checker, node, container?.node, kind);
        }
        transports.push({ node, row, urlNode, methodReason, container });
        if (urlTemplate === null) unresolved.push(unknown(
          root, file, node, "dynamic_transport_url",
          "transport URL is not a string, template, or module literal constant",
          row.url_expression, owner,
        ));
        if (methodReason) unresolved.push(unknown(
          root, file, node, "dynamic_fetch_method", methodReason,
          text(file, node.arguments?.[1]), owner,
        ));
      } else {
        const target = transportTarget(
          checker, node.expression, aliases, ts.isCallExpression(node) ? "call" : "new",
        );
        if (target) {
          suspiciousNodes.add(node);
          const urlNode = node.arguments?.[0];
          const urlTemplate = resolveUrl(checker, constants, urlNode);
          if (target.alias) {
            operations.push({
              expanded_wrapper: target.alias,
              kind: "unknown_wrapper_call",
              method: null,
              source: source(root, file, node),
              _transport_ref: null,
              url_template: urlTemplate,
            });
            unresolved.push(unknown(
              root, file, node, "unknown_wrapper_call", "aliased transport call",
              text(file, urlNode), target.alias,
            ));
          } else {
            const kind = target.kind === "fetch"
              ? "shadowed_fetch_call"
              : "shadowed_event_source_call";
            const owner = ownerName(node, functions);
            operations.push({
              kind,
              method: null,
              source: source(root, file, node),
              _transport_ref: null,
              url_template: urlTemplate,
              ...(owner ? { enclosing_function: owner } : {}),
            });
            unresolved.push(unknown(
              root, file, node, kind,
              `${target.kind === "fetch" ? "fetch call" : "EventSource construction"} resolves through a local, imported, parameter, method, or object binding`,
              text(file, node), owner,
            ));
          }
        }
      }
    }
    ts.forEachChild(node, collect);
  }
  collect(file);
  const direct = new Map();
  for (const transport of transports) {
    if (!transport.container?.candidate) continue;
    const list = direct.get(transport.container) || [];
    list.push(transport);
    direct.set(transport.container, list);
  }
  const wrappers = new Map();
  for (const info of functions.candidates) {
    const found = direct.get(info) || [];
    if (found.length === 1) {
      const transport = found[0];
      const urlValue = unwrap(transport.urlNode);
      const exact = urlValue && ts.isIdentifier(urlValue) &&
        info.parameters.includes(checker.getSymbolAtLocation(urlValue));
      let usesParameter = false;
      function inspect(node) {
        if (ts.isIdentifier(node) && info.parameters.includes(checker.getSymbolAtLocation(node))) {
          usesParameter = true;
        }
        ts.forEachChild(node, inspect);
      }
      if (transport.urlNode) inspect(transport.urlNode);
      if (exact) wrappers.set(info.symbol, {
        info,
        safe: transport.row.method !== null,
        reason: transport.row.method === null
          ? transport.methodReason || "wrapper transport method is not statically resolved"
          : null,
        transport,
      });
      else if (transport.row.url_template === null && usesParameter) wrappers.set(info.symbol, {
        info, safe: false, reason: "wrapper URL parameter is transformed", transport,
      });
    } else if (found.length > 1) wrappers.set(info.symbol, {
      info, safe: false, reason: "wrapper contains multiple direct transports", transport: null,
    });
  }
  function walkOwn(node, callback) {
    function visit(child) {
      if (child !== node && functionLike(child)) return;
      callback(child);
      ts.forEachChild(child, visit);
    }
    visit(node);
  }
  for (const info of functions.candidates) {
    if (wrappers.has(info.symbol)) continue;
    let reached;
    walkOwn(info.node, (node) => {
      if (reached || !ts.isCallExpression(node) || node.arguments.length === 0) return;
      const target = wrappers.get(symbol(checker, node.expression));
      const argument = unwrap(node.arguments[0]);
      if (
        target && argument && ts.isIdentifier(argument) &&
        info.parameters.includes(checker.getSymbolAtLocation(argument))
      ) reached = target;
    });
    if (reached) wrappers.set(info.symbol, {
      info,
      safe: false,
      reason: "wrapper reaches transport through another local wrapper",
      transport: reached.transport,
    });
  }
  function collectWrapperAliases(node) {
    if (
      ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) &&
      node.initializer && ts.isIdentifier(unwrap(node.initializer))
    ) {
      const target = wrappers.get(symbol(checker, node.initializer));
      if (target) {
        const aliasSymbol = checker.getSymbolAtLocation(node.name);
        wrappers.set(aliasSymbol, {
          info: { name: node.name.text },
          safe: false,
          reason: "wrapper is an alias of another local wrapper",
          transport: target.transport,
        });
        unresolved.push(unknown(
          root, file, node, "aliased_wrapper", "same-file wrapper aliases are not expanded",
          text(file, node), node.name.text,
        ));
      }
    }
    ts.forEachChild(node, collectWrapperAliases);
  }
  collectWrapperAliases(file);
  const safeDefinitions = new Set(
    [...wrappers.values()].filter((item) => item.safe)
      .map((item) => item.transport?.node.getStart(file)),
  );
  for (const transport of transports) {
    if (!safeDefinitions.has(transport.node.getStart(file))) operations.push({
      kind: "direct_transport",
      method: transport.row.method,
      source: { ...transport.row.source },
      _transport_ref: transport.row._transport_ref,
      url_template: transport.row.url_template,
    });
  }
  function wrapperCalls(node) {
    if (ts.isCallExpression(node)) {
      const callSymbol = symbol(checker, node.expression);
      const wrapper = wrappers.get(callSymbol);
      const imported = imports.get(callSymbol);
      if (wrapper) {
        const container = nearestFunction(node, functions);
        const containerWrapper = container ? wrappers.get(container.symbol) : undefined;
        if (containerWrapper?.reason !== "wrapper reaches transport through another local wrapper") {
          const urlNode = node.arguments[0];
          const urlTemplate = resolveUrl(checker, constants, urlNode);
          operations.push({
            expanded_wrapper: wrapper.info.name,
            kind: wrapper.safe ? "one_hop_wrapper_call" : "unknown_wrapper_call",
            method: wrapper.safe ? wrapper.transport.row.method : null,
            source: source(root, file, node),
            _transport_ref: wrapper.transport?.row._transport_ref || null,
            url_template: urlTemplate,
          });
          if (wrapper.safe && urlTemplate === null) unresolved.push(unknown(
            root, file, node, "dynamic_wrapper_call_url",
            "safe wrapper call URL is not statically resolvable",
            text(file, urlNode), wrapper.info.name,
          ));
          else if (!wrapper.safe) unresolved.push(unknown(
            root, file, node, "unknown_wrapper_call", wrapper.reason,
            text(file, urlNode), wrapper.info.name,
          ));
        }
      } else if (imported && !suspiciousNodes.has(node) && !aliases.has(callSymbol)) {
        const urlNode = node.arguments[0];
        const urlTemplate = resolveUrl(checker, constants, urlNode);
        if (
          urlTemplate !== null &&
          (urlTemplate.startsWith("/") || /^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(urlTemplate))
        ) {
          operations.push({
            expanded_wrapper: imported,
            kind: "unknown_wrapper_call",
            method: null,
            source: source(root, file, node),
            _transport_ref: null,
            url_template: urlTemplate,
          });
          unresolved.push(unknown(
            root, file, node, "unknown_wrapper_call", "imported wrapper call",
            text(file, urlNode), imported,
          ));
        }
      }
    }
    ts.forEachChild(node, wrapperCalls);
  }
  wrapperCalls(file);
  return {
    transports: transports.map((item) => item.row),
    operations,
    unresolved,
  };
}
function main() {
  const root = rootArgument(process.argv.slice(2));
  const names = frontendFiles(root);
  const program = ts.createProgram({
    rootNames: names,
    options: {
      target: ts.ScriptTarget.ES2020,
      lib: ["lib.es2020.d.ts", "lib.dom.d.ts", "lib.dom.iterable.d.ts"],
      module: ts.ModuleKind.ESNext,
      moduleResolution: ts.ModuleResolutionKind.Bundler,
      moduleDetection: ts.ModuleDetectionKind.Force,
      jsx: ts.JsxEmit.ReactJSX,
      noEmit: true,
      skipLibCheck: true,
      strict: true,
    },
  });
  const files = names.map((name) => program.getSourceFile(name));
  if (files.some((file) => !file)) die("TypeScript did not load every declared frontend file");
  const diagnostics = files.flatMap((file) => program.getSyntacticDiagnostics(file));
  if (diagnostics.length) {
    const diagnostic = diagnostics[0];
    const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, " ");
    const where = diagnostic.file && diagnostic.start !== undefined
      ? `${relative(root, diagnostic.file.fileName)}:${diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start).line + 1}`
      : "frontend";
    die(`TypeScript syntax error at ${where}: ${message}`);
  }
  const checker = program.getTypeChecker();
  const payload = {
    parser: "TypeScript compiler API",
    typescript_version: ts.version,
    files: names.map((name) => relative(root, name)),
    transports: [],
    operations: [],
    unresolved: [],
  };
  for (const file of files) {
    const facts = analyzeFile(root, file, checker);
    payload.transports.push(...facts.transports);
    payload.operations.push(...facts.operations);
    payload.unresolved.push(...facts.unresolved);
  }
  process.stdout.write(JSON.stringify(payload));
}
try {
  main();
} catch (error) {
  process.stderr.write(`frontend inventory failed: ${error?.stack || error}\n`);
  process.exit(1);
}
