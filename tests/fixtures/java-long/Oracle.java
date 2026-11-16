import java.io.BufferedReader;
import java.io.InputStreamReader;

// Handwritten primitive-long observations; no project parser or converter.
public final class Oracle {
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = input.readLine()) != null) {
            String[] fields = line.split(" ");
            int operation = Integer.parseInt(fields[0]);
            long a = Long.parseLong(fields[1]);
            long b = Long.parseLong(fields[2]);
            try {
                long value;
                switch (operation) {
                    case 0: value = a; break;
                    case 1: value = a + b; break;
                    case 2: value = a - b; break;
                    case 3: value = a * b; break;
                    case 4: value = -a; break;
                    case 5: value = a / b; break;
                    case 6: value = a % b; break;
                    case 7: value = a & b; break;
                    case 8: value = a | b; break;
                    case 9: value = a ^ b; break;
                    case 10: value = ~a; break;
                    case 11: value = a << b; break;
                    case 12: value = a >> b; break;
                    case 13: value = a >>> b; break;
                    case 14: value = (int) a; break;
                    case 15: value = (byte) a; break;
                    case 16: value = (short) a; break;
                    case 17: value = (char) a; break;
                    case 18: value = (long) (int) a; break;
                    case 19: value = Long.compare(a, b); break;
                    default: throw new IllegalArgumentException("unknown operation");
                }
                System.out.println(value);
            } catch (ArithmeticException error) {
                System.out.println("arithmetic");
            }
        }
    }
}
