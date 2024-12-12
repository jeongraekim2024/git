import os
import sys
import socket
import argparse
from struct import pack, unpack

# 기본 설정
DEFAULT_PORT = 69  # TFTP 기본 포트
BLOCK_SIZE = 512  # 데이터 블록 크기
DEFAULT_TRANSFER_MODE = 'octet'  # 전송 모드
TIMEOUT = 5  # 타임아웃(초)

# TFTP Opcode 정의
OPCODE = {'RRQ': 1, 'WRQ': 2, 'DATA': 3, 'ACK': 4, 'ERROR': 5}

# 오류 코드 및 메시지 정의
ERROR_CODE = {
    0: "Not defined, see error message (if any).",
    1: "File not found.",
    2: "Access violation.",
    3: "Disk full or allocation exceeded.",
    4: "Illegal TFTP operation.",
    5: "Unknown transfer ID.",
    6: "File already exists.",
    7: "No such user."
}

def create_socket():
    """소켓을 생성하고 타임아웃을 설정합니다."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)  # 타임아웃 설정
    return sock

def send_request(sock, opcode, filename, mode, server_address):
    """RRQ 또는 WRQ 메시지를 생성하여 전송합니다."""
    # opcode, filename, mode를 포함한 패킷 생성 및 전송
    message = pack(f'>h{len(filename)}sB{len(mode)}sB', opcode, filename.encode(), 0, mode.encode(), 0)
    sock.sendto(message, server_address)

def send_ack(sock, block_num, server_address):
    """ACK(확인 응답) 메시지를 전송합니다."""
    ack_message = pack('>hh', OPCODE['ACK'], block_num)  # ACK 메시지 생성
    sock.sendto(ack_message, server_address)

def send_data(sock, block_num, data_block, server_address):
    """DATA 메시지를 생성하여 전송합니다."""
    data_message = pack('>hh', OPCODE['DATA'], block_num) + data_block
    sock.sendto(data_message, server_address)

def receive_data(sock, expected_block_num):
    """데이터 수신 및 블록 번호 확인."""
    try:
        # 데이터 수신 및 패킷 디코딩
        data, server = sock.recvfrom(516)  # 최대 516바이트 수신 (헤더 4바이트 + 데이터 512바이트)
        opcode, block_num = unpack('>hh', data[:4])  # Opcode와 Block 번호 분리
        file_data = data[4:]  # 실제 파일 데이터
        return opcode, block_num, file_data, server
    except socket.timeout:
        # 타임아웃 처리
        print("타임아웃: 응답이 없습니다. 재시도 중...")
        return None, None, None, None

def download_file(sock, filename, server_address):
    """파일 다운로드 구현."""
    send_request(sock, OPCODE['RRQ'], filename, DEFAULT_TRANSFER_MODE, server_address)  # RRQ 메시지 전송

    with open(filename, 'wb') as file:  # 다운로드할 파일을 쓰기 모드로 엽니다.
        expected_block_num = 1
        while True:
            # 데이터 수신 및 블록 번호 확인
            opcode, block_num, file_data, server = receive_data(sock, expected_block_num)
            if opcode == OPCODE['DATA'] and block_num == expected_block_num:
                # 수신 데이터 저장 및 ACK 전송
                file.write(file_data)
                send_ack(sock, block_num, server)
                expected_block_num += 1
                if len(file_data) < BLOCK_SIZE:
                    # 마지막 블록 도착
                    print("파일 다운로드 완료.")
                    break
            elif opcode == OPCODE['ERROR']:
                # 오류 발생 시 메시지 출력
                print(ERROR_CODE.get(block_num, "알 수 없는 오류"))
                os.remove(filename)  # 임시로 생성된 파일 삭제
                break

def upload_file(sock, filename, server_address):
    """파일 업로드 구현."""
    if not os.path.exists(filename):
        print(f"파일 {filename}이(가) 존재하지 않습니다.")  # 파일 존재 여부 확인
        sys.exit(1)

    send_request(sock, OPCODE['WRQ'], filename, DEFAULT_TRANSFER_MODE, server_address)  # WRQ 메시지 전송

    with open(filename, 'rb') as file:  # 업로드할 파일을 읽기 모드로 엽니다.
        block_num = 1
        while True:
            data_block = file.read(BLOCK_SIZE)  # 블록 단위로 읽기
            send_data(sock, block_num, data_block, server_address)  # 데이터 전송
            try:
                opcode, ack_block_num, _, _ = receive_data(sock, block_num)
                if opcode == OPCODE['ACK'] and ack_block_num == block_num:
                    # ACK 수신 후 다음 블록 전송
                    block_num += 1
                    if len(data_block) < BLOCK_SIZE:
                        # 마지막 블록 전송 완료
                        print("파일 업로드 완료.")
                        break
            except socket.timeout:
                # 타임아웃 발생 시 현재 블록 재전송
                print(f"타임아웃: 블록 {block_num} 재전송.")
                continue

def main():
    # 명령줄 인자 파싱
    parser = argparse.ArgumentParser(
        description='TFTP 클라이언트 프로그램',
        usage="%(prog)s <host> {get,put} <filename> [-p PORT]"
    )
    parser.add_argument("host", help="서버 IP 주소", type=str)
    parser.add_argument("operation", help="'get' 또는 'put'", choices=['get', 'put'])
    parser.add_argument("filename", help="전송할 파일 이름", type=str)
    parser.add_argument("-p", "--port", help="서버 포트 (기본값: 69)", type=int, default=DEFAULT_PORT)

    if len(sys.argv) < 4:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    # 서버 주소와 포트를 설정
    server_address = (args.host, args.port)
    sock = create_socket()  # 소켓 생성

    if args.operation == 'get':
        download_file(sock, args.filename, server_address)  # 파일 다운로드
    elif args.operation == 'put':
        upload_file(sock, args.filename, server_address)  # 파일 업로드

if __name__ == "__main__":
    main()
