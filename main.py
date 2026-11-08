"""Single invocation for local Python and GitHub Actions."""
from longfor import longfor_sign
from bark_notify import notify_sign_result


def main():
    success,message,count,total=longfor_sign()
    print(message)
    notify_sign_result(message.split('\n'),success,count,total)
    return success


if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
