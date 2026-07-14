import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from aa_proxy import load_voice

def test_load_voice_traversal():
    # Valid
    try:
        load_voice('valid_voice-123')
        # We might get a FileNotFoundError, but that's fine. We just don't want a ValueError for valid format
    except ValueError as e:
        print("FAIL: valid voice id raised ValueError")
        return False
    except FileNotFoundError:
        pass
    except Exception as e:
        pass # could be no piper module, we don't care about that right now

    # Invalid - path traversal
    invalid_ids = ['../etc/passwd', '..\\windows\\system32', '/etc/shadow', 'valid..']
    for v_id in invalid_ids:
        try:
            load_voice(v_id)
            print(f"FAIL: invalid voice id {v_id} did not raise ValueError")
            return False
        except ValueError:
            pass # Expected
        except Exception as e:
            print(f"FAIL: invalid voice id {v_id} raised something else: {e}")
            return False

    print("SUCCESS: Path traversal prevented")
    return True

if __name__ == '__main__':
    if test_load_voice_traversal():
        sys.exit(0)
    else:
        sys.exit(1)
