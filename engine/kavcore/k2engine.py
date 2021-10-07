# -*- coding:utf-8 -*-
import glob
import mmap
import os
import StringIO
import datetime
import types

import k2kmdfile
import k2rsa

#Engine 클래스
class Engine:
    #클래스 초기화
    def __init__(self, debug=False):
        self.debug=debug    #디버깅 여부

        self.plugins_path=None  #플러그인 경로
        self.kmdfiles=[]    #우선순위가 기록된 kmd 리스트
        self.kmd_modules = []  # 메모리에 로딩된 모듈

        # 플러그 엔진의 가장 최신 시간 값을 가진다.
        # 초기값으로는 1980-01-01을 지정한다.
        self.max_datetime = datetime.datetime(1980, 1, 1, 0, 0, 0, 0)

    #주어진 경로에서 플러그인 엔진 로딩 준비
    def set_plugins(self, plugins_path):
        self.plugins_path=plugins_path  #플러그인 경로 저장

        #공개키 로딩
        pu = k2rsa.read_key(os.path.join(plugins_path, 'key.pkr'))

        if not pu:
            return False

        #우선순위 알아내기
        ret = self.__get_kmd_list(os.path.join(plugins_path, 'cloudbread.kmd'), pu)
        if not ret: #로딩할 kmd 파일이 없을 시
            return False

        if self.debug:
            print("[*] Cloudbread. kmd: ")
            print('     '+str(self.kmdfiles))

        # 우선순위대로 KMD 파일을 로딩한다.
        for kmd_name in self.kmdfiles:
            kmd_path = os.path.join(plugins_path, kmd_name)
            k=k2kmdfile.KMD(kmd_path, pu)   #모든 kmd 파일을 복호화
            module=k2kmdfile.load(kmd_name.split('.')[0], k.body)

            if module:  # 메모리 로딩 성공
                self.kmd_modules.append(module)
                # 메모리 로딩에 성공한 KMD에서 플러그 엔진의 시간 값 읽기
                self.__get_last_kmd_build_time(k)

        if self.debug:
            print("[*] kmd_modules: ")
            print('     '+str(self.kmd_modules))
            print("[*] Last updated %s UTC"%self.max_datetime.ctime())

        return True

    # 복호화 된 플러그인 엔진의 빌드 시간 값 중 최신 값을 보관
    # 입력값 : kmd_info - 복호화 된 플러그인 엔진 정보
    def __get_last_kmd_build_time(self, kmd_info):
        d_y, d_m, d_d = kmd_info.date
        t_h, t_m, t_s = kmd_info.time
        t_datetime = datetime.datetime(d_y, d_m, d_d, t_h, t_m, t_s)

        if self.max_datetime < t_datetime:
            self.max_datetime = t_datetime

    # 백신 엔진의 인스턴스를 생성
    def create_instance(self):
        ei = EngineInstance(self.plugins_path, self.max_datetime, self.debug)
        if ei.create(self.kmd_modules):
            return ei
        else:
            return None

    #플러그인 엔진의 로딩 우선순위 알아내는 함수
    def __get_kmd_list(self, cloudbread_kmd_file, pu):
        kmdfiles=[] #우선순위 목록

        k=k2kmdfile.KMD(cloudbread_kmd_file, pu)    #cloudbread.kmd 파일 복호화

        if k.body:  #cloudbread.kmd가 읽혔는지?
            msg=StringIO.StringIO(k.body)

            while True:
                line=msg.readline().strip() #엔터 제거

                if not line:    #읽을 내용이 없으면 종료
                    break
                elif line.find('.kmd') != -1:   # kmd가 포함되어 있으면 우선순위 목록에 추가
                    kmdfiles.append(line)
                else:
                    continue

        if len(kmdfiles):   #우선순위 목록에 하나라도 있다면 성송
            self.kmdfiles=kmdfiles
            return True
        else:
            return False



# EngineInstance 클래스
class EngineInstance:
    # 클래스 초기
    # 인자값 : plugins_path - 플러그인 엔진 경로
    #         temp_path    - 임시 폴더 클래스
    #         max_datetime - 플러그인 엔진의 최신 시간 값
    #         debug      - 디버그 여부
    def __init__(self, plugins_path, max_datetime, debug=False):
        self.debug = debug  # 디버깅 여부

        self.plugins_path = plugins_path  # 플러그인 경로
        self.max_datetime = max_datetime  # 플러그 엔진의 가장 최신 시간 값

        self.options={} #옵션
        self.set_options()  #기본 옵션 설정

        self.kavmain_inst=[]    #모든 플러그인의 KaVMain 인스턴스

        self.result={}
        self.identified_virus=set() #유니크한 악성코드 개수를 구하기 위해 사용

    def init(self):
        t_kavmain_inst=[]   #최종 인스턴스 리스트
        print(len(self.kavmain_inst))

        if self.debug:
            print('[*] KavMain.init(): ')

        for inst in self.kavmain_inst:
            try:
                #플러그인 엔진 init 함수 호출
                ret=inst.init(self.plugins_path)
                if not ret:
                    t_kavmain_inst.append(inst)
                    if self.debug:
                        print('[-] %s.init(): %d' %(inst.__module__, ret))
            except AttributeError:
                continue

        self.kavmain_inst=t_kavmain_inst    #최종 KavMain 인스턴스 등록

        if len(self.kavmain_inst):
            if self.debug:
                print('[*] Count of KavMain.init(): %d' % (len(self.kavmain_inst)))
            return True
        else:
            return False

    def uninit(self):
        if self.debug:
            print('[*] KavMain.uninit(): ')

        for inst in self.kavmain_inst:
            try:
                ret=inst.uninit()
                if self.debug:
                    print('[-] %s.uninit: %d' % (inst.__module__, ret))
            except AttributeError:
                continue

    def getinfo(self):
        ginfo = []  # 플러그인 엔진 정보

        if self.debug:
            print '[*] KavMain.getinfo() :'

        for inst in self.kavmain_inst:
            try:
                ret = inst.getinfo()
                ginfo.append(ret)

                if self.debug:
                    print('    [-] %s.getinfo() :' % inst.__module__)
                    for key in ret.keys():
                        print('        - %-10s : %s' % (key, ret[key]))
            except AttributeError:
                continue

        return ginfo


    # 백신 엔진의 악성코드 검사 결과를 초기화
    def set_result(self):
        self.result['Folders'] = 0  # 폴더 수
        self.result['Files'] = 0  # 파일 수
        self.result['Infected_files'] = 0  # 발견된 전체 악성코드 수 (감염)
        self.result['Identified_viruses'] = 0  # 발견된 유니크한 악성코드 수
        self.result['IO_errors'] = 0  # 파일 I/O 에러 발생 수

    # 백신 엔진의 악성코드 검사 결과
    def get_result(self):
        # 지금까지 발견한 유티크한 악성코드의 수를 카운트
        self.result['Identified_viruses'] = len(self.identified_virus)
        return self.result


    # 플러그인 엔진이 진단/치료 할 수 있는 악성코드 목록을 얻음
    # 리턴값 : 악성코드 목록 (콜백함수 사용시 아무런 값도 없음)
    def listvirus(self, *callback):
        vlist = []  # 진단/치료 가능한 악성코드 목록

        argc = len(callback)  # 가변인자 확인

        if argc == 0:  # 인자가 없으면
            cb_fn = None
        elif argc == 1:  # callback 함수가 존재하는지 체크
            cb_fn = callback[0]
        else:  # 인자가 너무 많으면 에러
            return []

        if self.debug:
            print('[*] KavMain.listvirus() :')

        for inst in self.kavmain_inst:
            try:
                ret = inst.listvirus()

                # callback 함수가 있다면 callback 함수 호출
                if isinstance(cb_fn, types.FunctionType):
                    cb_fn(inst.__module__, ret)
                else:  # callback 함수가 없으면 악성코드 목록을 누적하여 리턴
                    vlist += ret

                if self.debug:
                    print('    [-] %s.listvirus() :' % inst.__module__)
                    for vname in ret:
                        print('        - %s' % vname)
            except AttributeError:
                continue

        return vlist

    # 백신엔진의 인스턴스를 생성
    # 인자값 : kmd_modules - 메모리에 로딩된 KMD 모듈 리스트
    # 리턴값 : 성공 여부
    def create(self, kmd_modules):  # 백신 엔진 인스턴스를 생성
        for mod in kmd_modules:
            try:
                t = mod.KavMain()  # 각 플러그인 KavMain 인스턴스 생성
                self.kavmain_inst.append(t)
            except AttributeError:  # KavMain 클래스 존재하지 않음
                continue

        if len(self.kavmain_inst):  # KavMain 인스턴스가 하나라도 있으면 성공
            if self.debug:
                print('[*] Count of KavMain : %d' % (len(self.kavmain_inst)))
            return True
        else:
            return False

    # 플러그인 엔진에게 악성코드 검사를 요청
    # 입력값 : filename - 악성코 검사 대상 파일 또는 폴더 이름
    #          callback - 검사 시 출력 화면 관련 콜백 함수
    # 리턴값 : 0 - 성공
    #          1 - Ctrl+C를 이용해서 악성코드 검사 강제 종료
    def scan(self, filename, *callback):
        cb_fn=None  #콜백 함수

        # 악성코드 검사 결과
        ret_value = {
            'filename': '',  # 파일 이름
            'result': False,  # 악성코드 발견 여부
            'virus_name': '',  # 발견된 악성코드 이름
            'virus_id': -1,  # 악성코드 ID
            'engine_id': -1  # 악성코드를 발견한 플러그인 엔진 ID
        }

        #가변 인자 확인
        argc=len(callback)

        if argc==1: #callback 함수가 존재하는가?
            cb_fn=callback[0]
        elif argc>1:    #인자가 너무 많으면 에러
            return -1

        #검사 대상 리스트에 파일을 등록
        file_scan_list = [filename]

        while len(file_scan_list):
            try:
                real_name = file_scan_list.pop(0)   #검사대상 파일을 하나 가짐

                # 폴더면 내부 파일리스트만 검사 대상 리스트에 등록
                if os.path.isdir(real_name):
                    if real_name[-1]==os.sep:
                        real_name=real_name[:-1]

                    # 콜백 호출 또는 검사 리턴값 생성
                    ret_value['result'] = False  # 폴더이므로 악성코드 없음
                    ret_value['filename'] = real_name  # 검사 파일 이름

                    self.result['Folders'] += 1   #폴더 개수 카운트

                    if self.options['opt_list']:  # 옵션 내용 중 모든 리스트 출력인가?
                        if isinstance(cb_fn, types.FunctionType):   #콜백함수 존재?
                            cb_fn(ret_value)    #콜백함수 호출

                    #폴더 안의 파일들을 검사 대상 리스트에 추가
                    flist=glob.glob(real_name+os.sep+'*')
                    file_scan_list=flist+file_scan_list
                elif os.path.isfile(real_name): #검사 대상이 파일인가?
                    ret, vname, mid, eid=self.__scan_file(real_name)

                    if ret: #악성코드 진단 개수 카운트
                        self.result['Infected_files']+=1
                        self.identified_virus.update([vname])

                    self.result['Files'] += 1   #파일 개수 카운트

                    #콜백 호출 또는 검사 리턴값 생성
                    ret_value['result'] = ret  # 악성코드 발견 여부
                    ret_value['engine_id'] = eid  # 엔진 ID
                    ret_value['virus_name'] = vname  # 에러 메시지로 대체
                    ret_value['virus_id'] = mid  # 악성코드 ID
                    ret_value['filename']=real_name #검사 파일 이름

                    if self.options['opt_list']:  # 모든 리스트 출력인가?
                        if isinstance(cb_fn, types.FunctionType):
                            cb_fn(ret_value)
                    else:   #d아니면 악성코드인 것만 출력
                        if ret_value['result']:
                            if isinstance(cb_fn, types.FunctionType):
                                cb_fn(ret_value)
            except KeyboardInterrupt:
                return 1    #키보드 종료

        return 0    #정상적으로 검사 종료


    def __scan_file(self, filename):
        if self.debug:
            print('[*] KavMain.scan(): ')

        try:
            ret=False
            vname=''
            mid=-1
            eid=-1

            fp=open(filename, 'rb')
            mm=mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)
            for i,inst in enumerate(self.kavmain_inst):
                try:
                    ret,vname, mid=inst.scan(mm, filename)
                    if ret: #악성코드를 발견하면 추가 악성코드 검사를 중단
                        eid=i   #악성코드를 발견한 플러그인 엔진 ID

                        if self.debug:
                            print('[-] %s.scan(): %s' % (inst.__module__, vname))
                            break
                except AttributeError:
                    continue

            if mm:
                mm.close()
            if fp:
                fp.close()

            return ret, vname, mid, eid
        except IOError:
            self.result['IO_errors'] +=1   #파일 I/O Error 발생수

        return False, '', -1, -1




    # 플러그인 엔진에게 악성코드 치료를 요청한다.
    # 입력값 : filename   - 악성코드 치료 대상 파일 이름
    #          malware_id - 감염된 악성코드 ID
    #          engine_id  - 악성코드를 발견한 플러그인 엔진 ID
    # 리턴값 : 악성코드 치료 성공 여부
    def disinfect(self, filename, malware_id, engine_id):
        ret = False

        if self.debug:
            print('[*] KavMain.disinfect() :')

        try:
            # 악성코드를 진단한 플러그인 엔진에게만 치료를 요청
            inst = self.kavmain_inst[engine_id]
            ret = inst.disinfect(filename, malware_id)

            if self.debug:
                print('    [-] %s.disinfect() : %s' % (inst.__module__, ret))
        except AttributeError:
            pass

        return ret


    def get_version(self):
        return self.max_datetime

    def set_options(self, options=None):
        if options:
            self.options['opt_list']=options.opt_list
        else:
            self.options['opt_list']=False
        return True

    # 진단 가능한 악성코드 수
    def get_signum(self):
        signum=0 #진단/치료 가능한 악성코드 수

        for inst in self.kavmain_inst:
            try:
                ret=inst.getinfo()

                if 'sig_num' in ret:
                    signum+=ret['sig_num']
            except AttributeError:
                continue

        return signum
