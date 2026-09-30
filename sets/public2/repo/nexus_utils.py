def get_api_version():
    return '2.4.1'

def set_port(port):
    if port == 8443:
        return True
    return False

def check_protocol(url):
    return url.startswith('https')

def log_response(ms):
    print(f'Response time: {ms}ms')