import re
import time
import bs4
import requests
from bs4 import BeautifulSoup as bs


class CookieExpired(Exception):
    pass


class RequestLimitExceed(Exception):
    pass


class BaekjoonSession:
    groupId: int
    requestLimit: int
    throttlePerRequestAsMilliseconds: int

    __session: requests.Session
    __requestCount: int

    def __init__(self, groupId: int, cookies=None, requestLimit=20, throttlePerRequestAsMilliseconds=50):
        """
        백준 전용 세션을 생성합니다.

        :param groupId: 백준 그룹의 아이디입니다
        :param requestLimit: 프로그램에서 최대로 사용할 수 있는 요청 횟수입니다. 초과할 시 프로그램이 종료됩니다.
        :param throttlePerRequestAsMilliseconds: 각 요청당 딜레이를 설정합니다. millisecond 단위로 설정합니다.
        """
        self.groupId = groupId
        self.requestLimit = requestLimit
        self.throttlePerRequestAsMilliseconds = throttlePerRequestAsMilliseconds
        self.__session = requests.Session()
        self.__session.cookies.update(cookies)
        self.__session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36'
        })

        # 실제 요청 횟수가 기록되는 변수
        self.__requestCount = 0

    def get(self, url):
        """
        주어진 URL에 GET 리퀘스트를 보내어 응답을 받아옵니다.
        내부적으로 requests.Session 객체를 사용하며, 요청 횟수 및 쓰로틀링을 위해
        wrapping한 함수입니다.

        :param url: 불러올 URL
        """
        # 요청 전에, request limit를 넘지 않는지 검사.
        if self.__requestCount >= self.requestLimit:
            print(f'[Collector] 요청 횟수를 초과했습니다. 최대 요청 횟수={self.requestLimit}')
            raise RequestLimitExceed()

        # 첫 번째 요청이 아니면 쓰로틀링 걸기
        if self.__requestCount != 0 and self.throttlePerRequestAsMilliseconds > 0:
            print(
                f'[Collector] Throttle {self.throttlePerRequestAsMilliseconds} ms ...')
            time.sleep(self.throttlePerRequestAsMilliseconds / 1000)

        result = self.__session.get(url)
        self.__requestCount += 1

        print(
            f'[Collector] "GET {url}" {result.status_code} request_remain={self.requestLimit - self.__requestCount}')

        return result

    def ensureLogin(self):
        """
        로그인이 되어있는지 확인합니다. 로그인이 되어있지 않을 시 CookieExpired 예외를 발생시킵니다.

        :raises CookieExpired: 로그인이 되어있지 않을 시 발생
        """
        soup = bs4.BeautifulSoup(
            self.get(f'https://www.acmicpc.net/group/{self.groupId}').text)

        if '채점 현황' not in [e.text for e in soup.find('ul', {'class': 'nav nav-pills'}).find_all('li')]:
            print('[Collector] 로그인이 되어있지 않습니다. 쿠키 정보를 확인해주세요.')
            raise CookieExpired

        print('[Collector] Succesfully checked login state')

    def __parseSubmissionFromTableRowElement(self, submissionTag):
        tagStr = str(submissionTag)

        username = re.search(r'/user/(\w+)', tagStr)
        if not username:
            return None
        username = username[1]

        # 제출 번호, 유저 이름, 문제 번호, 문제 이름
        submission = {
            'id': int(re.search(r'solution-(\d+)', tagStr)[1]),
            'username': username,
            'problemId': int(re.search(r'/problem/(\d+)', tagStr)[1]),
            # '?' at '.+?' means non-greedy (https://stackoverflow.com/questions/766372/python-non-greedy-regexes)
            'problemName': re.search(r'title="(.+?)"', tagStr)[1],
        }

        # 티어 정보를 사용할 수 있다면 티어 정보도 추가
        # 1=Bronze V, 2=Bronze IV, 3=Bronze III, 4=Bronze II, 5=Bronze I
        # 6=Silver V, 7=Silver IV ...
        tier = re.search(r'/tier/(\d+)\.svg', tagStr)
        if tier is not None:
            submission['tier'] = int(tier[1])

        # 결과 정보 파싱 및 저장
        resultTag = submissionTag.find(class_='result-text')

        submission.update({
            'resultCode': '-'.join(resultTag.attrs['class'][1].strip().split('-')[1:]).upper(),
            'resultMessage': ' '.join(resultTag.text.split(u'\xa0'))
        })

        # 메모리, 시간, 언어, 코드 길이 정보
        memory, timeRecord, language, length = [
            el.text for el in submissionTag.contents[4:8]]

        submission.update({
            'memory': int(memory) if memory else None,
            'time': int(timeRecord) if timeRecord else None,
            'language': language,
            'length': int(length) if length else None,
            'when': submissionTag.contents[8].contents[0].attrs['title']
        })

        return submission

    def fetchSubmissions(self, top=None):
        url = f'https://www.acmicpc.net/status?group_id={self.groupId}'
        if top is not None:
            url += f'&top={top}'

        html = self.get(url)
        soup = bs(html.text, 'html.parser')
        submissionsTags = soup.find('tbody').find_all('tr')

        # 채점 중, 채점 준비중 등 채점이 완료되지 않은 채점 발견 시 다음 번에 크롤링하도록 함
        # (이번 크롤링에서는 제외)
        # 가장 아래의 제출부터 체크하고, 채점이 완료되지 않은 제출 발견 시 바로 break
        submissions = []
        for submission in reversed([self.__parseSubmissionFromTableRowElement(tag) for tag in submissionsTags]):
            if submission is None:
                continue

            if submission['resultCode'] in ['WAIT', 'REJUDGE-WAIT', 'COMPILE', 'JUDGING']:
                break

            submissions.insert(0, submission)

        return submissions

    def fetchSubmissionsUntil(self, submissionId):
        submissions = []
        top = None
        page = 1
        print(f'[Collector] Fetch until submissionId={submissionId}')

        while True:
            print(f'[Collector] Try to fetch page={page}, top={top}')

            try:
                for submission in self.fetchSubmissions(top):
                    if submission['id'] <= submissionId:
                        return submissions

                    submissions.append(submission)

                # do not include 'top' submission
                top = submissions[-1]['id'] - 1
                page += 1

            # 요청 횟수 초과 시 루프 탈출 & submissions 반환
            except RequestLimitExceed:
                return submissions

    def fetchProblem(self, problemId):
        html = self.get(f'https://www.acmicpc.net/problem/{problemId}')
        soup = bs(html.text, 'html.parser')

        return {
            'name': soup.find(id='problem_title').text,
            'tier': int(re.search(r'tier/(\d+)\.svg', soup.find(class_='solvedac-tier')['src'])[1]),
            'tags': [e.find('a').text for e in soup.find(id='problem_tags').find_all('li')],
        }
