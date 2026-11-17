import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Iterator;
import java.util.List;
import org.apache.commons.collections4.queue.CircularFifoQueue;

// NEX-authored adapter: execute the unmodified Apache4.6.0 implementation.
// TSV is a host-owned command protocol; JSON observations use decimal strings
// for integral values, matching nex.wire/2 without a JSON library dependency.
public final class Oracle {
    private static String quote(String value) {
        StringBuilder result = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '\\' || c == '"') result.append('\\').append(c);
            else if (c < 32) result.append(String.format("\\u%04x", (int)c));
            else result.append(c);
        }
        return result.append('"').toString();
    }
    private static String strings(List<String> values) {
        StringBuilder result = new StringBuilder("[");
        for (String value : values) {
            if (result.length() != 1) result.append(',');
            result.append(quote(value));
        }
        return result.append(']').toString();
    }
    private static List<String> numbers(Collection<Long> values) {
        List<String> result = new ArrayList<>();
        for (Long value : values) result.add(value.toString());
        return result;
    }
    private static List<String> number(Long value) {
        List<String> result = new ArrayList<>();
        if (value != null) result.add(value.toString());
        return result;
    }
    private static List<String> flag(boolean value) {
        List<String> result = new ArrayList<>();
        result.add(Boolean.toString(value));
        return result;
    }
    private static void observe(String trace, int step, String operation, String outcome,
                                List<String> values, CircularFifoQueue<Long> queue) {
        System.out.println("{\"trace\":" + quote(trace) + ",\"step\":" + quote(Integer.toString(step))
            + ",\"operation\":" + quote(operation) + ",\"outcome\":" + quote(outcome)
            + ",\"values\":" + strings(values) + ",\"size\":" + quote(Integer.toString(queue.size()))
            + ",\"capacity\":" + quote(Integer.toString(queue.maxSize()))
            + ",\"empty\":" + queue.isEmpty() + ",\"full\":" + queue.isFull()
            + ",\"at_capacity\":" + queue.isAtFullCapacity()
            + ",\"contents\":" + strings(numbers(queue)) + "}");
    }
    public static void main(String[] args) throws Exception {
        BufferedReader input = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        CircularFifoQueue<Long> queue = new CircularFifoQueue<>(1);
        CircularFifoQueue<Long> alias = queue;
        Iterator<Long> cursor = queue.iterator(), cursorAlias = cursor;
        List<Long> saved = new ArrayList<>();
        String trace = ""; int step = 0; String line;
        while ((line = input.readLine()) != null) {
            String[] fields = line.split("\t", -1);
            if (fields[0].equals("trace")) {
                if (fields.length != 2 || !fields[1].matches("[a-z0-9_-]+"))
                    throw new Exception("invalid host trace name");
                trace = fields[1]; step = 0; queue = new CircularFifoQueue<>(1); alias = queue;
                cursor = queue.iterator(); cursorAlias = cursor; saved = new ArrayList<>();
                continue;
            }
            if (trace.isEmpty()) throw new Exception("missing host trace");
            String op = fields[0], outcome = "unit";
            List<String> values = new ArrayList<>();
            List<Long> arguments = new ArrayList<>();
            for (int i = 1; i < fields.length; i++) arguments.add(Long.parseLong(fields[i]));
            try {
                switch (op) {
                    case "new": queue = new CircularFifoQueue<>(Math.toIntExact(arguments.get(0))); break;
                    case "default": queue = new CircularFifoQueue<>(); break;
                    case "from": queue = new CircularFifoQueue<>(arguments); break;
                    case "from_null": queue = new CircularFifoQueue<Long>((Collection<Long>)null); break;
                    case "copy": queue = new CircularFifoQueue<>(queue); break;
                    case "alias": alias = queue; break;
                    case "add": outcome = "bool"; values = flag(queue.add(arguments.get(0))); break;
                    case "offer": outcome = "bool"; values = flag(queue.offer(arguments.get(0))); break;
                    case "add_alias": outcome = "bool"; values = flag(alias.add(arguments.get(0))); break;
                    case "add_null": outcome = "bool"; values = flag(queue.add(null)); break;
                    case "offer_null": outcome = "bool"; values = flag(queue.offer(null)); break;
                    case "clear": queue.clear(); break;
                    case "peek": {
                        Long value = queue.peek(); outcome = value == null ? "none" : "number"; values = number(value); break;
                    }
                    case "poll": {
                        Long value = queue.poll(); outcome = value == null ? "none" : "number"; values = number(value); break;
                    }
                    case "remove": outcome = "number"; values = number(queue.remove()); break;
                    case "element": outcome = "number"; values = number(queue.element()); break;
                    case "get": outcome = "number"; values = number(queue.get(Math.toIntExact(arguments.get(0)))); break;
                    case "size": outcome = "number"; values = number((long)queue.size()); break;
                    case "max_size": outcome = "number"; values = number((long)queue.maxSize()); break;
                    case "empty": outcome = "bool"; values = flag(queue.isEmpty()); break;
                    case "full": outcome = "bool"; values = flag(queue.isFull()); break;
                    case "at_capacity": outcome = "bool"; values = flag(queue.isAtFullCapacity()); break;
                    case "iterator": cursor = queue.iterator(); break;
                    case "iterator_alias": cursorAlias = cursor; break;
                    case "has_next": outcome = "bool"; values = flag(cursor.hasNext()); break;
                    case "next": outcome = "number"; values = number(cursor.next()); break;
                    case "next_alias": outcome = "number"; values = number(cursorAlias.next()); break;
                    case "iterator_remove": cursor.remove(); break;
                    case "iterator_remove_alias": cursorAlias.remove(); break;
                    case "snapshot": saved = new ArrayList<>(queue); break;
                    case "saved": outcome = "items"; values = numbers(saved); break;
                    case "alias_items": outcome = "items"; values = numbers(alias); break;
                    case "same_queue": outcome = "bool"; values = flag(queue == alias); break;
                    case "same_iterator": outcome = "bool"; values = flag(cursor == cursorAlias); break;
                    default: throw new Exception("unknown host operation " + op);
                }
            } catch (RuntimeException error) {
                outcome = error.getClass().getSimpleName(); values = new ArrayList<>();
            }
            observe(trace, step++, op, outcome, values, queue);
        }
    }
}
