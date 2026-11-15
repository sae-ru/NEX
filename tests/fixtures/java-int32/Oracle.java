import java.io.BufferedReader;
import java.io.InputStreamReader;

// Handwritten semantic oracle. It does not parse or translate project source.
public final class Oracle {
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = input.readLine()) != null) {
            String[] fields = line.split(" ");
            int operation = Integer.parseInt(fields[0]);
            long rawA = Long.parseLong(fields[1]);
            long rawB = Long.parseLong(fields[2]);
            int a = (int) rawA;
            int b = (int) rawB;
            try {
                int result;
                switch (operation) {
                    case 0: result = a; break;
                    case 1: result = a + b; break;
                    case 2: result = a - b; break;
                    case 3: result = a * b; break;
                    case 4: result = -a; break;
                    case 5: result = a / b; break;
                    case 6: result = a % b; break;
                    case 7: result = a & b; break;
                    case 8: result = a | b; break;
                    case 9: result = a ^ b; break;
                    case 10: result = ~a; break;
                    case 11: result = a << rawB; break;
                    case 12: result = a >> rawB; break;
                    case 13: result = a >>> rawB; break;
                    case 14: result = (byte) a; break;
                    case 15: result = (short) a; break;
                    case 16: result = (char) a; break;
                    default: throw new IllegalArgumentException("unknown operation");
                }
                System.out.println(result);
            } catch (ArithmeticException error) {
                System.out.println("arithmetic");
            }
        }
    }
}
