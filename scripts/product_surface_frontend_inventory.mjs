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
function fixedUrl(checker, constants, node) {
  const value = unwrap(node);
  const fixed = literal(checker, constants, value);
  if (fixed !== undefined) return fixed;
  if (!value || !ts.isTemplateExpression(value)) return undefined;
  let result = value.head.text;
  for (const span of value.templateSpans) {
    const replacement = literal(checker, constants, span.expression);
    if (replacement === undefined) return undefined;
    result += replacement;
    result += span.literal.text;
  }
  return result;
}
function resolveUrl(checker, constants, node) {
  const fixed = fixedUrl(checker, constants, node);
  if (fixed !== undefined) return fixed;
  const value = unwrap(node);
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
    const hasThisParameter = node.parameters.some(
      (parameter) => ts.isIdentifier(parameter.name) && parameter.name.text === "this",
    );
    const parameters = node.parameters.map((parameter, index) => {
      const symbols = new Set();
      function collectSymbols(child) {
        if (ts.isIdentifier(child)) {
          const found = checker.getSymbolAtLocation(child);
          if (found) symbols.add(found);
        }
        ts.forEachChild(child, collectSymbols);
      }
      collectSymbols(parameter.name);
      return {
        index,
        node: parameter,
        supported: !hasThisParameter && ts.isIdentifier(parameter.name) &&
          parameter.name.text !== "this" && !parameter.dotDotDotToken &&
          !parameter.initializer && !parameter.questionToken,
        symbol: ts.isIdentifier(parameter.name)
          ? checker.getSymbolAtLocation(parameter.name)
          : undefined,
        symbols,
      };
    });
    const parameterBySymbol = new Map();
    for (const parameter of parameters) {
      for (const found of parameter.symbols) parameterBySymbol.set(found, parameter);
    }
    const info = { node, name, parameters, parameterBySymbol, candidate,
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
  // Imports from within the project (relative specifiers) are candidate
  // wrapper modules we simply couldn't see into; imports from a package
  // (react, etc.) are framework/library calls out of this tool's declared
  // scope (frontendFiles() already excludes node_modules outright). Tracked
  // separately from `imports` so the opaque-call heuristic below can stay
  // scoped to project-owned code without touching the existing literal-URL
  // classification, which never needed the distinction.
  const localImports = new Set();
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
    const specifier = ts.isStringLiteralLike(statement.moduleSpecifier)
      ? statement.moduleSpecifier.text
      : undefined;
    const isLocal = specifier !== undefined &&
      (specifier.startsWith("./") || specifier.startsWith("../"));
    for (const name of names) {
      const importSymbol = checker.getSymbolAtLocation(name);
      imports.set(importSymbol, name.text);
      if (isLocal) localImports.add(importSymbol);
    }
  }
  return { constants, imports, localImports };
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
  const { constants, imports, localImports } = moduleFacts(checker, file);
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
  function directUrlSource(info, transport) {
    const urlValue = unwrap(transport.urlNode);
    const urlSymbol = urlValue && ts.isIdentifier(urlValue)
      ? checker.getSymbolAtLocation(urlValue)
      : undefined;
    const exactParameter = urlSymbol
      ? info.parameterBySymbol.get(urlSymbol)
      : undefined;
    if (exactParameter) {
      return exactParameter.supported
        ? { kind: "parameter", index: exactParameter.index }
        : {
            kind: "unknown",
            reason: "wrapper URL parameter shape is unsupported",
          };
    }
    const usedParameters = new Set();
    function inspect(node) {
      if (ts.isIdentifier(node)) {
        const parameter = info.parameterBySymbol.get(checker.getSymbolAtLocation(node));
        if (parameter) usedParameters.add(parameter);
      }
      ts.forEachChild(node, inspect);
    }
    if (transport.urlNode) inspect(transport.urlNode);
    if (usedParameters.size) {
      return {
        kind: "unknown",
        reason: "wrapper URL parameter is transformed",
      };
    }
    const fixed = fixedUrl(checker, constants, transport.urlNode);
    if (fixed !== undefined) return { kind: "fixed", value: fixed };
    return undefined;
  }
  function mergeUrlSources(sources) {
    let merged;
    for (const candidate of sources) {
      if (!merged) {
        merged = { ...candidate };
        continue;
      }
      if (
        merged.kind === "unknown" || candidate.kind === "unknown" ||
        merged.kind !== candidate.kind ||
        (merged.kind === "parameter" && merged.index !== candidate.index) ||
        (merged.kind === "fixed" && merged.value !== candidate.value)
      ) {
        merged = { kind: "unknown" };
      }
    }
    return merged || { kind: "unknown" };
  }
  function parameterForUrlSource(info, urlSource) {
    return urlSource.kind === "parameter"
      ? info.parameters.find((parameter) => parameter.index === urlSource.index)
      : undefined;
  }
  const directWrappers = new Map();
  for (const info of functions.candidates) {
    const found = direct.get(info) || [];
    if (found.length === 1) {
      const transport = found[0];
      const urlSource = directUrlSource(info, transport);
      if (!urlSource) continue;
      const urlParameter = parameterForUrlSource(info, urlSource);
      directWrappers.set(info.symbol, {
        info,
        safe: urlSource.kind !== "unknown" && transport.row.method !== null,
        reason: urlSource.kind === "unknown"
          ? urlSource.reason
          : transport.row.method === null
          ? transport.methodReason || "wrapper transport method is not statically resolved"
          : null,
        transport,
        urlParameterIndex: urlParameter?.index,
        _ambiguousTransport: false,
        _reachableTransports: new Set([transport]),
        _urlSource: urlSource,
        dependsOnLocalWrapper: false,
      });
    } else if (found.length > 1) {
      const urlSource = mergeUrlSources(
        found.map(
          (transport) => directUrlSource(info, transport) || { kind: "unknown" },
        ),
      );
      const parameter = parameterForUrlSource(info, urlSource);
      directWrappers.set(info.symbol, {
        info,
        safe: false,
        reason: "wrapper contains multiple direct transports",
        transport: null,
        urlParameterIndex: parameter?.supported ? parameter.index : undefined,
        _ambiguousTransport: true,
        _reachableTransports: new Set(found),
        _urlSource: urlSource,
        dependsOnLocalWrapper: false,
      });
    }
  }
  function walkOwn(node, callback) {
    function visit(child) {
      if (child !== node && functionLike(child)) return;
      callback(child);
      ts.forEachChild(child, visit);
    }
    visit(node);
  }
  function dependencyUrlSource(target, call, info) {
    if (target._urlSource?.kind === "fixed") {
      return { ...target._urlSource };
    }
    if (target._urlSource?.kind !== "parameter") {
      return { kind: "unknown" };
    }
    const argument = unwrap(call.arguments[target._urlSource.index]);
    const parameter = argument && ts.isIdentifier(argument)
      ? info.parameterBySymbol.get(checker.getSymbolAtLocation(argument))
      : undefined;
    if (parameter?.supported) {
      return { kind: "parameter", index: parameter.index };
    }
    const fixed = fixedUrl(checker, constants, argument);
    return fixed === undefined
      ? { kind: "unknown" }
      : { kind: "fixed", value: fixed };
  }
  const wrapperAliases = [];
  function collectWrapperAliasDeclarations(node) {
    if (
      ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) &&
      node.initializer && ts.isIdentifier(unwrap(node.initializer))
    ) {
      const aliasSymbol = checker.getSymbolAtLocation(node.name);
      const targetSymbol = symbol(checker, node.initializer);
      if (aliasSymbol && targetSymbol) wrapperAliases.push({
        aliasSymbol,
        targetSymbol,
        node,
        name: node.name.text,
      });
    }
    ts.forEachChild(node, collectWrapperAliasDeclarations);
  }
  collectWrapperAliasDeclarations(file);
  function aliasWrapper(alias, target) {
    return {
      info: { name: alias.name },
      safe: false,
      reason: "wrapper is an alias of another local wrapper",
      transport: target.transport,
      urlParameterIndex: target.urlParameterIndex,
      _ambiguousTransport: target._ambiguousTransport,
      _reachableTransports: new Set(target._reachableTransports),
      _urlSource: { ...target._urlSource },
      dependsOnLocalWrapper: true,
    };
  }
  // Resolve from a complete previous-pass snapshot.  Each pass can discover
  // one more function or alias dependency layer; classifying only after
  // unioning every reachable transport keeps branching wrappers independent
  // of declaration/call order.  The total graph-node count bounds convergence
  // and leaves transport-free cycles unresolved.
  let wrappers = new Map(directWrappers);
  const wrapperPassLimit = functions.candidates.length + wrapperAliases.length;
  for (let pass = 0; pass < wrapperPassLimit; pass += 1) {
    const previous = wrappers;
    const next = new Map();
    for (const info of functions.candidates) {
      const base = directWrappers.get(info.symbol);
      const reachableTransports = new Set(
        base?._reachableTransports || [],
      );
      const urlSources = base ? [{ ...base._urlSource }] : [];
      let ambiguousTransport = base?._ambiguousTransport || false;
      let dependsOnLocalWrapper = false;
      walkOwn(info.node, (node) => {
        if (!ts.isCallExpression(node)) return;
        const target = previous.get(symbol(checker, node.expression));
        if (!target) return;
        dependsOnLocalWrapper = true;
        ambiguousTransport ||= target._ambiguousTransport;
        for (const transport of target._reachableTransports) {
          reachableTransports.add(transport);
        }
        urlSources.push(dependencyUrlSource(target, node, info));
      });
      if (!base && !dependsOnLocalWrapper) continue;

      ambiguousTransport ||= reachableTransports.size > 1;
      const urlSource = mergeUrlSources(urlSources);
      const urlParameter = parameterForUrlSource(info, urlSource);
      const urlParameterIndex = urlParameter?.index;
      const transport = !ambiguousTransport && reachableTransports.size === 1
        ? reachableTransports.values().next().value
        : null;
      next.set(info.symbol, {
        info,
        safe: dependsOnLocalWrapper ? false : base.safe,
        reason: dependsOnLocalWrapper
          ? ambiguousTransport
            ? "wrapper reaches multiple transports through local wrapper dependencies"
            : "wrapper reaches transport through another local wrapper"
          : base.reason,
        transport,
        urlParameterIndex,
        _ambiguousTransport: ambiguousTransport,
        _reachableTransports: reachableTransports,
        _urlSource: urlSource,
        dependsOnLocalWrapper,
      });
    }
    for (const alias of wrapperAliases) {
      const target = previous.get(alias.targetSymbol);
      if (target) next.set(alias.aliasSymbol, aliasWrapper(alias, target));
    }
    wrappers = next;
  }
  for (const alias of wrapperAliases) {
    if (!wrappers.has(alias.aliasSymbol)) continue;
    unresolved.push(unknown(
      root, file, alias.node, "aliased_wrapper", "same-file wrapper aliases are not expanded",
      text(file, alias.node), alias.name,
    ));
  }
  const wrapperCallEdges = [];
  function collectWrapperCallEdges(node) {
    if (ts.isCallExpression(node)) {
      const targetSymbol = symbol(checker, node.expression);
      if (wrappers.has(targetSymbol)) {
        const container = nearestFunction(node, functions);
        const sourceSymbol = container?.symbol && wrappers.has(container.symbol)
          ? container.symbol
          : undefined;
        wrapperCallEdges.push({ sourceSymbol, targetSymbol });
      }
    }
    ts.forEachChild(node, collectWrapperCallEdges);
  }
  collectWrapperCallEdges(file);
  const wrapperGraph = new Map(
    [...wrappers.keys()].map((wrapperSymbol) => [wrapperSymbol, new Set()]),
  );
  for (const edge of wrapperCallEdges) {
    if (edge.sourceSymbol) wrapperGraph.get(edge.sourceSymbol)?.add(edge.targetSymbol);
  }
  for (const alias of wrapperAliases) {
    if (wrappers.has(alias.aliasSymbol) && wrappers.has(alias.targetSymbol)) {
      wrapperGraph.get(alias.aliasSymbol)?.add(alias.targetSymbol);
    }
  }
  // Recursive edges are component-internal implementation detail, not proof
  // that an external/root operation represents the component.  Tarjan's
  // partition lets suppression preserve uncalled recursive roots while still
  // collapsing a component reached by a real outer call.
  const wrapperIndex = new Map();
  const wrapperLowLink = new Map();
  const wrapperStack = [];
  const wrappersOnStack = new Set();
  const componentByWrapper = new Map();
  const componentMembers = [];
  let nextWrapperIndex = 0;
  function connectWrapper(wrapperSymbol) {
    wrapperIndex.set(wrapperSymbol, nextWrapperIndex);
    wrapperLowLink.set(wrapperSymbol, nextWrapperIndex);
    nextWrapperIndex += 1;
    wrapperStack.push(wrapperSymbol);
    wrappersOnStack.add(wrapperSymbol);
    for (const targetSymbol of wrapperGraph.get(wrapperSymbol) || []) {
      if (!wrapperIndex.has(targetSymbol)) {
        connectWrapper(targetSymbol);
        wrapperLowLink.set(
          wrapperSymbol,
          Math.min(wrapperLowLink.get(wrapperSymbol), wrapperLowLink.get(targetSymbol)),
        );
      } else if (wrappersOnStack.has(targetSymbol)) {
        wrapperLowLink.set(
          wrapperSymbol,
          Math.min(wrapperLowLink.get(wrapperSymbol), wrapperIndex.get(targetSymbol)),
        );
      }
    }
    if (wrapperLowLink.get(wrapperSymbol) !== wrapperIndex.get(wrapperSymbol)) return;
    const component = new Set();
    const componentIndex = componentMembers.length;
    while (wrapperStack.length) {
      const member = wrapperStack.pop();
      wrappersOnStack.delete(member);
      componentByWrapper.set(member, componentIndex);
      component.add(member);
      if (member === wrapperSymbol) break;
    }
    componentMembers.push(component);
  }
  for (const wrapperSymbol of wrapperGraph.keys()) {
    if (!wrapperIndex.has(wrapperSymbol)) connectWrapper(wrapperSymbol);
  }
  const representedComponents = new Set();
  for (const edge of wrapperCallEdges) {
    const targetComponent = componentByWrapper.get(edge.targetSymbol);
    const sourceComponent = edge.sourceSymbol === undefined
      ? undefined
      : componentByWrapper.get(edge.sourceSymbol);
    if (sourceComponent !== targetComponent) representedComponents.add(targetComponent);
  }
  const componentEdges = new Map(
    componentMembers.map((_, component) => [component, new Set()]),
  );
  for (const [sourceSymbol, targets] of wrapperGraph) {
    const sourceComponent = componentByWrapper.get(sourceSymbol);
    for (const targetSymbol of targets) {
      const targetComponent = componentByWrapper.get(targetSymbol);
      if (sourceComponent !== targetComponent) {
        componentEdges.get(sourceComponent)?.add(targetComponent);
      }
    }
  }
  const representedQueue = [...representedComponents];
  while (representedQueue.length) {
    const component = representedQueue.pop();
    for (const targetComponent of componentEdges.get(component) || []) {
      if (representedComponents.has(targetComponent)) continue;
      representedComponents.add(targetComponent);
      representedQueue.push(targetComponent);
    }
  }
  function wrapperIsRepresented(wrapperSymbol) {
    return representedComponents.has(componentByWrapper.get(wrapperSymbol));
  }
  function sameWrapperComponent(left, right) {
    return left !== undefined && right !== undefined &&
      componentByWrapper.get(left) === componentByWrapper.get(right);
  }
  // A parameter-sourced safe wrapper used to be suppressed unconditionally
  // here (pre-7b8b6786 behavior for the fixed-url case too), on the
  // assumption a safe wrapper is always represented by some call. That
  // assumption is false for an exported wrapper that is never called in
  // this file: it silently erased the definition's own transport row with
  // nothing left to represent it. Route parameter-kind through the same
  // Tarjan-component wrapperIsRepresented gate the fixed-url case already
  // uses, so an uncalled wrapper's transport survives regardless of its
  // URL-source kind.
  const representedDefinitions = new Set();
  for (const transport of transports) {
    const containerSymbol = transport.container?.symbol;
    const wrapper = containerSymbol
      ? wrappers.get(containerSymbol)
      : undefined;
    if (wrapper && wrapperIsRepresented(containerSymbol)) {
      representedDefinitions.add(transport.node.getStart(file));
    }
  }
  for (const transport of transports) {
    if (!representedDefinitions.has(transport.node.getStart(file))) operations.push({
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
        const containerSymbol = containerWrapper ? container.symbol : undefined;
        const containerIsRepresented = wrapperIsRepresented(containerSymbol);
        const internalRecursiveCall = sameWrapperComponent(containerSymbol, callSymbol);
        if (!containerIsRepresented && !internalRecursiveCall) {
          const urlNode = wrapper._urlSource?.kind !== "parameter"
            ? undefined
            : node.arguments[wrapper.urlParameterIndex];
          const resolvedUrl = wrapper._urlSource?.kind === "fixed"
            ? wrapper._urlSource.value
            : resolveUrl(checker, constants, urlNode);
          const operationMethod = wrapper.transport?.row.method ?? null;
          const urlTemplate = wrapper.safe || operationMethod === null
            ? resolvedUrl
            : null;
          operations.push({
            expanded_wrapper: wrapper.info.name,
            kind: wrapper.safe ? "one_hop_wrapper_call" : "unknown_wrapper_call",
            method: operationMethod,
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
      } else if (
        imported && !suspiciousNodes.has(node) && !aliases.has(callSymbol) &&
        localImports.has(callSymbol)
      ) {
        // A call through a project-local import we cannot see into (the
        // wrapper's own file is analyzed separately, symbol-by-symbol, so
        // its classification never crosses files) used to land here only
        // when the URL argument was a literal that happened to look like a
        // path or a scheme. A non-literal argument (parameter passthrough,
        // a computed expression) made resolveUrl return null and the call
        // site vanished from both operations and unresolved -- the live
        // network call disappeared instead of surfacing as unresolved.
        // Emit the same taxonomy row regardless of whether the URL resolved
        // to something path-shaped; only the populated url_template differs.
        const urlNode = node.arguments[0];
        const urlValue = urlNode ? unwrap(urlNode) : undefined;
        const isCallbackArgument = urlValue !== undefined &&
          (ts.isArrowFunction(urlValue) || ts.isFunctionExpression(urlValue));
        if (urlNode && !isCallbackArgument) {
          const urlTemplate = resolveUrl(checker, constants, urlNode);
          const looksLikeUrl = urlTemplate !== null &&
            (urlTemplate.startsWith("/") || /^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(urlTemplate));
          operations.push({
            expanded_wrapper: imported,
            kind: "unknown_wrapper_call",
            method: null,
            source: source(root, file, node),
            _transport_ref: null,
            url_template: looksLikeUrl ? urlTemplate : null,
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
