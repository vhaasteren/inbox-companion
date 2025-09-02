#!/usr/bin/env node
/* eslint-disable no-console */
import { fileURLToPath, pathToFileURL } from "url";
import { dirname, resolve, relative, join, parse as parsePath } from "path";
import { readdirSync, statSync, existsSync } from "fs";

function findTS(startDir) {
  // Walk upwards to find frontend-local TypeScript
  let dir = resolve(startDir);
  while (true) {
    const candidate = join(dir, "node_modules", "typescript", "lib", "typescript.js");
    if (existsSync(candidate)) return pathToFileURL(candidate).href;
    const { root } = parsePath(dir);
    if (dir === root) break;
    dir = dirname(dir);
  }
  return null;
}

async function loadTS(startDir) {
  const localUrl = findTS(startDir);
  if (localUrl) return (await import(localUrl)).default ?? (await import(localUrl));
  try {
    return (await import("typescript")).default;
  } catch {
    console.error(
      "[api] TypeScript not found. Run `npm --prefix frontend install`, or ensure typescript is available."
    );
    process.exit(1);
  }
}

const exts = new Set([".ts", ".tsx"]);
function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = resolve(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) out.push(...walk(p));
    else {
      const i = name.lastIndexOf(".");
      const ext = i >= 0 ? name.slice(i) : "";
      if (exts.has(ext)) out.push(p);
    }
  }
  return out;
}

function hasModifier(node, kind, ts) {
  return node.modifiers?.some(m => m.kind === kind);
}

async function run(rootArg) {
  const root = resolve(rootArg);
  const ts = await loadTS(root);

  const files = walk(root);
  if (files.length === 0) return;

  const program = ts.createProgram({
    rootNames: files,
    options: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.ESNext,
      jsx: ts.JsxEmit.ReactJSX,
      strict: true,
      skipLibCheck: true
    }
  });
  const checker = program.getTypeChecker();

  for (const sourceFile of program.getSourceFiles()) {
    if (sourceFile.isDeclarationFile) continue;
    if (!sourceFile.fileName.startsWith(root)) continue;

    const rel = relative(process.cwd(), sourceFile.fileName);
    const out = [];

    const typeText = (node, fallback = "any") => {
      try {
        const t = checker.getTypeAtLocation(node);
        const s = checker.typeToString(
          t,
          node,
          ts.TypeFormatFlags.NoTruncation | ts.TypeFormatFlags.WriteArrowStyleSignature
        );
        return s || fallback;
      } catch {
        return fallback;
      }
    };

    const paramList = (params) =>
      params.map(p => {
        const name = p.name.getText(sourceFile);
        const optional = p.questionToken ? "?" : "";
        const type = p.type ? p.type.getText(sourceFile) : typeText(p);
        const def = p.initializer ? "=" + p.initializer.getText(sourceFile) : "";
        const spread = p.dotDotDotToken ? "..." : "";
        return `${spread}${name}${optional}: ${type}${def}`;
      }).join(", ");

    const fnSig = (name, node, paramsNode, returnTypeNode) => {
      const params = paramList(paramsNode.parameters ?? paramsNode);
      const ret = returnTypeNode ? returnTypeNode.getText(sourceFile) : typeText(node);
      return `function ${name}(${params}) -> ${ret}`;
    };

    const methodSig = (name, node) => {
      const params = paramList(node.parameters);
      const ret = node.type ? node.type.getText(sourceFile) : typeText(node);
      const asyncPrefix = hasModifier(node, ts.SyntaxKind.AsyncKeyword, ts) ? "async " : "";
      return `${asyncPrefix}${name}(${params}) -> ${ret}`;
    };

    function visit(node) {
      // function declarations (incl. default export)
      if (ts.isFunctionDeclaration(node) && node.name) {
        const exp = hasModifier(node, ts.SyntaxKind.ExportKeyword, ts) ? "export " : "";
        const dflt = hasModifier(node, ts.SyntaxKind.DefaultKeyword, ts) ? "default " : "";
        out.push(`${exp}${dflt}${fnSig(node.name.getText(sourceFile), node, node, node.type)}`);
      }

      // export const foo = (…)=>… / function expression
      if (ts.isVariableStatement(node) && hasModifier(node, ts.SyntaxKind.ExportKeyword, ts)) {
        for (const decl of node.declarationList.declarations) {
          const name = decl.name.getText(sourceFile);
          const init = decl.initializer;
          if (init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init))) {
            out.push(`export ${fnSig(name, init, init, init.type)}`);
          }
        }
      }

      // classes + methods (incl. default export)
      if (ts.isClassDeclaration(node) && node.name) {
        const exp = hasModifier(node, ts.SyntaxKind.ExportKeyword, ts) ? "export " : "";
        const dflt = hasModifier(node, ts.SyntaxKind.DefaultKeyword, ts) ? "default " : "";
        const cname = node.name.getText(sourceFile);
        const methods = [];
        for (const m of node.members) {
          if (ts.isMethodDeclaration(m) && m.name) {
            methods.push(`  ${methodSig(m.name.getText(sourceFile), m)}`);
          }
        }
        if (methods.length) {
          out.push(`${exp}${dflt}class ${cname}:`);
          out.push(...methods);
        }
      }

      // Type surface: exported interfaces and type aliases
      if (ts.isInterfaceDeclaration(node) && hasModifier(node, ts.SyntaxKind.ExportKeyword, ts)) {
        out.push(`export interface ${node.name.getText(sourceFile)}`);
      }
      if (ts.isTypeAliasDeclaration(node) && hasModifier(node, ts.SyntaxKind.ExportKeyword, ts)) {
        out.push(`export type ${node.name.getText(sourceFile)} = ${node.type.getText(sourceFile)}`);
      }

      ts.forEachChild(node, visit);
    }

    ts.forEachChild(sourceFile, visit);
    if (out.length) {
      console.log(`===== ${rel} =====`);
      for (const line of out) console.log(line);
      console.log();
    }
  }
}

const roots = process.argv.slice(2);
if (roots.length === 0) {
  console.error("Usage: ts_api.mjs <root_dir>");
  process.exit(2);
}
for (const r of roots) {
  await run(r);
}

