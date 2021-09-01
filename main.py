import os
import json
import sys
from baekjoon import BaekjoonSession, CookieExpired, RequestLimitExceed
from dotenv import load_dotenv


def updateSubmissions(session: BaekjoonSession):
    """
    submissions.json 파일을 최신화합니다.

    :param session: 백준에 요청을 보낼 수 있도록 BaekjoonSession 객체를 주어야 합니다.
    """
    with open('submissions.json', mode='r+', encoding='UTF-8') as submissionsJson:
        # 최근 제출들을 가져옵니다.
        submissions = json.load(submissionsJson)

        top = submissions[0]['id']
        recentSubmissions = session.fetchSubmissionsUntil(top)

        # submissions.json 파일의 상태가 최신이면 아무것도 하지 않음
        if len(recentSubmissions) == 0:
            print('submissions.json 파일 상태가 최신입니다.')

        # 써야 할 데이터가 있으면 쓰기
        else:
            submissionsJson.seek(0)
            submissionsJson.write(json.dumps(
                recentSubmissions + submissions, indent='\t', ensure_ascii=False))
            submissionsJson.truncate()
            print(f'성공적으로 크롤링을 완료하였습니다. {len(recentSubmissions)}건 추가됨')


def updateProblems(session: BaekjoonSession):
    """
    competitions.json 파일 내의 문제들 중 problems.json 에 없는 문제들을 업데이트합니다.

    :param session: 백준에 요청을 보낼 수 있도록 BaekjoonSession 객체를 주어야 합니다.
    """
    # competitions.json 파일을 읽어 problems.json에 어떤 문제가 없는지 확인합니다
    competitions = json.load(
        open('competitions.json', mode='r', encoding='UTF-8'))
    problemsDiscovered = {}

    with open('problems.json', mode='r+', encoding='UTF-8') as problemsJson:
        problemsKnown = {int(problemId): problemData for problemId,
                         problemData in json.load(problemsJson).items()}

        try:
            # 가장 최신의 competition 부터 처리하기 위해 reverse
            for competition in reversed(competitions):
                for problem in competition['problems']:
                    # 이미 알고 있는 문제는 넘어가도 OK
                    if problem in problemsKnown:
                        continue

                    # 새로 fetch 한 문제!
                    problemsDiscovered[problem] = session.fetchProblem(problem)

        except RequestLimitExceed:
            # 요청 횟수가 너무 많았으니 다음 번에 또 요청
            pass

        # 새롭게 fetch 한 문제가 있다면 write
        if len(problemsDiscovered) > 0:
            problemsKnown.update(problemsDiscovered)
            problemsJson.seek(0)
            problemsJson.write(json.dumps(
                dict(sorted(problemsKnown.items())), indent='\t', ensure_ascii=False))
            problemsJson.truncate()
            print(f'문제 정보들을 {len(problemsDiscovered)}건 추가하였습니다.')


try:
    load_dotenv()

    # 환경변수에서 설정 정보들을 가져옵니다.
    # GROUP_ID: 백준 그룹 ID
    # BOJ_AUTO_LOGIN: 로그인 관련 쿠키 값
    # ONLINE_JUDGE: 로그인 관련 쿠키 값
    GROUP_ID = os.getenv('GROUP_ID')
    BOJ_AUTO_LOGIN = os.getenv('BOJ_AUTO_LOGIN')
    ONLINE_JUDGE = os.getenv('ONLINE_JUDGE')

    if GROUP_ID is None or BOJ_AUTO_LOGIN is None or ONLINE_JUDGE is None:
        print(f'환경 변수 설정이 필요합니다. 환경 변수 설정 후 프로그램을 실행해주세요.')
        sys.exit(1)

    cookies = {
        'bojautologin': BOJ_AUTO_LOGIN,
        'OnlineJudge': ONLINE_JUDGE
    }

    session = BaekjoonSession(GROUP_ID, cookies)

    # 로그인 상태를 확인
    # 로그인이 안되어 있을 시 CookieExpired 에러를 발생시켜 프로그램 중단
    session.ensureLogin()

    # submissions.json 최신화
    updateSubmissions(session)

    # problems.json 최신화
    updateProblems(session)

except CookieExpired:
    sys.exit(1)  # 로그인 실패로 인한 종료는 정상 종료가 아님
