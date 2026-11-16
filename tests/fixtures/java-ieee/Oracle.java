import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.Locale;

// Handwritten primitive observations, not a Java project parser/converter.
public final class Oracle {
    static String h32(int bits) { return String.format(Locale.ROOT, "%08x", bits); }
    static String h64(long bits) { return String.format(Locale.ROOT, "%016x", bits); }
    static String f32(float value) { return h32(Float.floatToIntBits(value)); }
    static String f64(double value) { return h64(Double.doubleToLongBits(value)); }
    static String observe32(String op, String left, String right) {
        if (op.equals("from_int")) return f32((float) Integer.parseInt(left));
        if (op.equals("from_long")) return f32((float) Long.parseLong(left));
        int raw = Integer.parseUnsignedInt(left, 16);
        float a = Float.intBitsToFloat(raw);
        switch (op) {
            case "raw": return h32(raw);
            case "canonical": return f32(a);
            case "neg_raw": return h32(raw ^ Integer.MIN_VALUE);
            case "abs_raw": return h32(raw & Integer.MAX_VALUE);
            case "neg": return f32(-a);
            case "classify": return Float.isNaN(a) ? "nan" : Float.isInfinite(a) ? "infinity" :
                a == 0 ? "zero" : (raw & 0x7f800000) == 0 ? "subnormal" : "normal";
            case "to_int": return Integer.toString((int) a);
            case "to_long": return Long.toString((long) a);
            case "convert": return f64((double) a);
        }
        float b = Float.intBitsToFloat(Integer.parseUnsignedInt(right, 16));
        switch (op) {
            case "add": return f32(a + b);
            case "sub": return f32(a - b);
            case "mul": return f32(a * b);
            case "div": return f32(a / b);
            case "rem": return f32(a % b);
            case "eq": return Boolean.toString(a == b);
            case "ne": return Boolean.toString(a != b);
            case "lt": return Boolean.toString(a < b);
            case "le": return Boolean.toString(a <= b);
            case "gt": return Boolean.toString(a > b);
            case "ge": return Boolean.toString(a >= b);
            case "compare": return Integer.toString(Float.compare(a, b));
            default: throw new IllegalArgumentException(op);
        }
    }
    static String observe64(String op, String left, String right) {
        if (op.equals("from_int")) return f64((double) Integer.parseInt(left));
        if (op.equals("from_long")) return f64((double) Long.parseLong(left));
        long raw = Long.parseUnsignedLong(left, 16);
        double a = Double.longBitsToDouble(raw);
        switch (op) {
            case "raw": return h64(raw);
            case "canonical": return f64(a);
            case "neg_raw": return h64(raw ^ Long.MIN_VALUE);
            case "abs_raw": return h64(raw & Long.MAX_VALUE);
            case "neg": return f64(-a);
            case "classify": return Double.isNaN(a) ? "nan" : Double.isInfinite(a) ? "infinity" :
                a == 0 ? "zero" : (raw & 0x7ff0000000000000L) == 0 ? "subnormal" : "normal";
            case "to_int": return Integer.toString((int) a);
            case "to_long": return Long.toString((long) a);
            case "convert": return f32((float) a);
        }
        double b = Double.longBitsToDouble(Long.parseUnsignedLong(right, 16));
        switch (op) {
            case "add": return f64(a + b);
            case "sub": return f64(a - b);
            case "mul": return f64(a * b);
            case "div": return f64(a / b);
            case "rem": return f64(a % b);
            case "eq": return Boolean.toString(a == b);
            case "ne": return Boolean.toString(a != b);
            case "lt": return Boolean.toString(a < b);
            case "le": return Boolean.toString(a <= b);
            case "gt": return Boolean.toString(a > b);
            case "ge": return Boolean.toString(a >= b);
            case "compare": return Integer.toString(Double.compare(a, b));
            default: throw new IllegalArgumentException(op);
        }
    }
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = input.readLine()) != null) {
            String[] fields = line.split(" ");
            String right = fields.length == 4 ? fields[3] : "0";
            System.out.println(fields[0].equals("32") ? observe32(fields[1], fields[2], right) :
                observe64(fields[1], fields[2], right));
        }
    }
}
