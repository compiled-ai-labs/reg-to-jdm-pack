package io.compiledai.feel;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.time.temporal.TemporalAccessor;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.camunda.dmn.DmnEngine;
import org.camunda.dmn.parser.ParsedDmn;
import org.camunda.feel.api.EvaluationFailure;
import org.camunda.feel.api.EvaluationResult;
import org.camunda.feel.api.FeelEngineApi;
import org.camunda.feel.api.FeelEngineBuilder;
import org.camunda.feel.api.ParseResult;
import scala.util.Either;

/**
 * JSON lines on stdin, one answer per line on stdout. No state besides the loaded DMN.
 *
 * <pre>
 *   {"op": "load",  "xml": "..."}                         parse a DMN file (XSD + FEEL)
 *   {"op": "eval",  "decision": "id", "input": {...}}     evaluate a decision of the loaded DMN
 *   {"op": "parse", "expr": "...", "unary": false}        parse one FEEL expression
 *   {"op": "expr",  "expr": "...", "context": {...}}      evaluate one FEEL expression
 *   {"op": "version"}
 * </pre>
 *
 * The DMN engine is built as Zeebe builds it (DmnScalaDecisionEngine: new
 * DmnEngine.Builder().build()). Answers: {"ok": true, "value": ..., "failures": [...]} or
 * {"ok": false, "error": "..."}. "failures" are the engine's suppressed failures: an error the
 * engine turned into null instead of stopping.
 */
public final class Runner {
  private static final ObjectMapper JSON =
      new ObjectMapper().enable(JsonGenerator.Feature.WRITE_BIGDECIMAL_AS_PLAIN);

  private final DmnEngine dmnEngine = new DmnEngine.Builder().build();
  private final FeelEngineApi feel = FeelEngineBuilder.forJava().build();
  private ParsedDmn dmn;

  public static void main(String[] args) throws Exception {
    Runner runner = new Runner();
    PrintStream out = new PrintStream(System.out, true, StandardCharsets.UTF_8);
    BufferedReader in =
        new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
    String line;
    while ((line = in.readLine()) != null) {
      if (line.isBlank()) {
        continue;
      }
      ObjectNode answer;
      try {
        answer = runner.handle(JSON.readTree(line));
      } catch (Exception e) {
        answer = JSON.createObjectNode();
        answer.put("ok", false);
        answer.put("error", e.getClass().getSimpleName() + ": " + e.getMessage());
      }
      out.println(JSON.writeValueAsString(answer));
    }
  }

  private ObjectNode handle(JsonNode req) throws Exception {
    String op = req.path("op").asText();
    ObjectNode answer = JSON.createObjectNode();
    switch (op) {
      case "version" -> {
        answer.put("ok", true);
        answer.put("value", "dmn-engine "
            + pomVersion("org.camunda.bpm.extension.dmn.scala/dmn-engine")
            + ", feel-engine " + pomVersion("org.camunda.feel/feel-engine"));
      }
      case "load" -> {
        byte[] xml = req.path("xml").asText().getBytes(StandardCharsets.UTF_8);
        Either<DmnEngine.Failure, ParsedDmn> parsed =
            dmnEngine.parse(new ByteArrayInputStream(xml));
        if (parsed.isLeft()) {
          return fail(answer, parsed.left().get().message());
        }
        dmn = parsed.right().get();
        List<Object> ids = new ArrayList<>();
        dmn.decisionsById().keys().foreach(k -> ids.add(k));
        ids.sort(null);
        answer.put("ok", true);
        answer.set("value", JSON.valueToTree(ids));
      }
      case "eval" -> {
        if (dmn == null) {
          return fail(answer, "no DMN loaded");
        }
        Map<String, Object> input = toJava(req.path("input"));
        Either<DmnEngine.EvalFailure, DmnEngine.EvalResult> result =
            dmnEngine.eval(dmn, req.path("decision").asText(), input);
        if (result.isLeft()) {
          return fail(answer, result.left().get().failure().message());
        }
        answer.put("ok", true);
        answer.set("value", JSON.valueToTree(plain(result.right().get().value())));
      }
      case "parse" -> {
        String expr = req.path("expr").asText();
        ParseResult parsed = req.path("unary").asBoolean(false)
            ? feel.parseUnaryTests(expr)
            : feel.parseExpression(expr);
        if (parsed.isFailure()) {
          return fail(answer, String.valueOf(parsed.failure()));
        }
        answer.put("ok", true);
      }
      case "expr" -> {
        Map<String, Object> context = toJava(req.path("context"));
        EvaluationResult result = feel.evaluateExpression(req.path("expr").asText(), context);
        if (result.isFailure()) {
          return fail(answer, String.valueOf(result.failure()));
        }
        answer.put("ok", true);
        answer.set("value", JSON.valueToTree(plain(result.result())));
        List<String> failures = new ArrayList<>();
        for (EvaluationFailure f : result.getSuppressedFailures()) {
          failures.add(f.failureMessage());
        }
        answer.set("failures", JSON.valueToTree(failures));
      }
      default -> {
        return fail(answer, "unknown op " + op);
      }
    }
    return answer;
  }

  private static String pomVersion(String artifact) throws java.io.IOException {
    java.util.Properties props = new java.util.Properties();
    try (var in = Runner.class.getResourceAsStream(
        "/META-INF/maven/" + artifact + "/pom.properties")) {
      if (in == null) {
        return "unknown";
      }
      props.load(in);
    }
    return props.getProperty("version", "unknown");
  }

  private static ObjectNode fail(ObjectNode answer, String message) {
    answer.put("ok", false);
    answer.put("error", message);
    return answer;
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> toJava(JsonNode node) {
    if (node == null || node.isMissingNode() || node.isNull()) {
      return new LinkedHashMap<>();
    }
    return JSON.convertValue(node, Map.class);
  }

  /** Scala and FEEL result values as plain JSON values. Temporal values as ISO strings. */
  private static Object plain(Object v) {
    if (v == null || v instanceof String || v instanceof Boolean) {
      return v;
    }
    if (v instanceof scala.math.BigDecimal bd) {
      return bd.bigDecimal();
    }
    if (v instanceof Number) {
      return v;
    }
    if (v instanceof TemporalAccessor) {
      return v.toString();
    }
    if (v instanceof scala.Option<?> opt) {
      return opt.isEmpty() ? null : plain(opt.get());
    }
    if (v instanceof scala.collection.Map<?, ?> m) {
      Map<String, Object> out = new LinkedHashMap<>();
      m.foreach(t -> out.put(String.valueOf(t._1()), plain(t._2())));
      return out;
    }
    if (v instanceof scala.collection.Iterable<?> it) {
      List<Object> out = new ArrayList<>();
      it.foreach(x -> out.add(plain(x)));
      return out;
    }
    if (v instanceof Map<?, ?> m) {
      Map<String, Object> out = new LinkedHashMap<>();
      m.forEach((k, x) -> out.put(String.valueOf(k), plain(x)));
      return out;
    }
    if (v instanceof Iterable<?> it) {
      List<Object> out = new ArrayList<>();
      it.forEach(x -> out.add(plain(x)));
      return out;
    }
    return v.toString();
  }
}
