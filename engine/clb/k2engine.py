# -*- coding:utf-8 -*-
import glob
import mmap
import os
import StringIO
import datetime
import tempfile
import types

import clbfile
import rsa
import file
import menu

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
        pu = rsa.to_rsa_key(os.path.join(plugins_path, 'key.pkr'))

        if not pu:
            return False

        #우선순위 알아내기
        ret = self.__get_kmd_list(os.path.join(plugins_path, 'cloudbread.clb'), pu)

        if not ret: #로딩할 kmd 파일이 없을 시
            return False

        if self.debug:
            print("[*] Cloudbread. clb: ")
            print('     '+str(self.kmdfiles))


        # 우선순위대로 KMD 파일을 로딩한다.
        for kmd_name in self.kmdfiles:
            kmd_path = os.path.join(plugins_path, kmd_name)
            k=clbfile.CLB(kmd_path, pu)   #모든 kmd 파일을 복호화
            module=clbfile.memory_loading(kmd_name.split('.')[0], k.body)

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

        k=clbfile.CLB(cloudbread_kmd_file, pu)    #cloudbread.kmd 파일 복호화

        if k.body:  #cloudbread.kmd가 읽혔는지?
            msg=StringIO.StringIO(k.body)

            while True:
                line=msg.readline().strip() #엔터 제거

                if not line:    #읽을 내용이 없으면 종료
                    break
                elif line.find('.clb') != -1:   # kmd가 포함되어 있으면 우선순위 목록에 추가
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

        self.update_info=[]

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
        self.result['Packed'] = 0  # 압축 파일 수
        self.result['Infected_files'] = 0  # 발견된 전체 악성코드 수 (감염)
        self.result['Identified_viruses'] = 0  # 발견된 유니크한 악성코드 수
        self.result['Disinfected_files'] = 0  # 치료한 파일 수
        self.result['Deleted_files'] = 0  # 삭제한 파일 수
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
        self.update_info=[]
        scan_callback_fn=None   #악성코드 검사 콜백 함수
        disinfect_callback_fn=None  #악성코드 치료 콜백 함수
        update_callback_fn=None #악성코드 압축 최종 치료 콜백 함수

        # 악성코드 검사 결과
        ret_value = {
            'filename': '',  # 파일 이름
            'result': False,  # 악성코드 발견 여부
            'virus_name': '',  # 발견된 악성코드 이름
            'virus_id': -1,  # 악성코드 ID
            'engine_id': -1  # 악성코드를 발견한 플러그인 엔진 ID
        }

        try:  # 콜백 함수 저장
            scan_callback_fn = callback[0]
            disinfect_callback_fn = callback[1]
            update_callback_fn = callback[2]
        except IndexError:
            pass

        #가변 인자 확인
        argc=len(callback)

        if argc==1: #callback 함수가 존재하는가?
            cb_fn=callback[0]
        elif argc>1:    #인자가 너무 많으면 에러
            return -1

        #1. 검사 대상 리스트에 파일을 등록
        file_info=file.FileStruct(filename)
        file_scan_list=[file_info]

        while len(file_scan_list):
            try:
                t_file_info=file_scan_list.pop(0) #검사대상 파일을 하나 가짐
                real_name = t_file_info.get_target_file()

                # 폴더면 내부 파일리스트만 검사 대상 리스트에 등록
                if os.path.isdir(real_name):
                    if real_name[-1]==os.sep:
                        real_name=real_name[:-1]

                    # 콜백 호출 또는 검사 리턴값 생성
                    ret_value['result'] = False  # 폴더이므로 악성코드 없음
                    ret_value['filename'] = real_name  # 검사 파일 이름
                    ret_value['file_struct'] = t_file_info  # 검사 파일 이름

                    self.result['Folders'] += 1   #폴더 개수 카운트

                    if self.options['opt_list']:  # 옵션 내용 중 모든 리스트 출력인가?
                        if isinstance(cb_fn, types.FunctionType):   #콜백함수 존재?
                            scan_callback_fn(ret_value)    #콜백함수 호출

                    #폴더 안의 파일들을 검사 대상 리스트에 추가
                    flist=glob.glob(real_name+os.sep+'*')
                    tmp_flist=[]

                    for rfname in flist:
                        tmp_info=file.FileStruct(rfname)
                        tmp_flist.append(tmp_info)

                    file_scan_list=tmp_flist + file_scan_list

                # 검사 대상이 파일인가? 또는 압축해제 대상인가?
                elif os.path.isfile(real_name) or t_file_info.bool_zip():
                    self.result['Files'] += 1   #파일 개수 카운트

                    #압축된 파일이면 해제하기
                    ret=self.unarc(t_file_info)
                    if ret:
                        t_file_info=ret #압축 결과물이 존재하면 파일정보 교체

                    #2. 포맷 분석
                    ff=self.format(t_file_info)

                    #파일로 악성코드 검사
                    ret, vname, mid, eid=self.__scan_file(t_file_info, ff)

                    if ret: #악성코드 진단 개수 카운트
                        self.result['Infected_files']+=1
                        self.identified_virus.update([vname])


                    #콜백 호출 또는 검사 리턴값 생성
                    ret_value['result'] = ret  # 악성코드 발견 여부
                    ret_value['engine_id'] = eid  # 엔진 ID
                    ret_value['virus_name'] = vname  # 에러 메시지로 대체
                    ret_value['virus_id'] = mid  # 악성코드 ID
                    ret_value['file_struct']=t_file_info #검사 파일 이름

                    if ret_value['result']: #악성코드가 발견 됐다?!
                        if isinstance(scan_callback_fn, types.FunctionType):
                            action_type=scan_callback_fn(ret_value)

                        if action_type == menu.MENU_QUIT:  #종료할거임?
                            return 0
                        self.__disinfect_process(ret_value, disinfect_callback_fn, action_type)
                    else:
                        if self.options['opt_list']:  # 모든 리스트 출력인가?
                            if isinstance(scan_callback_fn, types.FunctionType):
                                scan_callback_fn(ret_value)
                        else:   #아니면 악성코드인 것만 출력
                            if ret_value['result']:
                                if isinstance(cb_fn, types.FunctionType):
                                    scan_callback_fn(ret_value)

                      #압축 파일 최종 치료 정리
                    self.__update_process(t_file_info, update_callback_fn)

                    if not ret:
                        arc_file_list=self.arclist(t_file_info, ff)
                        if len(arc_file_list):
                            file_scan_list=arc_file_list+file_scan_list
            except KeyboardInterrupt:
                return 1    #키보드 종료

        self.__update_process(None, update_callback_fn, True)   #최종 파일 정리

        return 0    #정상적으로 검사 종료

    def __scan_file(self, file_struct, fileformat):
        if self.debug:
            print('[*] KavMain.scan(): ')

        fp=None
        mm=None

        try:
            ret = False
            vname = ''
            mid = -1
            eid = -1

            filename=file_struct.get_target_file() #검사 대상 파일 이름 추출
            filename_ex=file_struct.get_zip_structure_file()   #압축 내부 파일명

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
            self.options['opt_arc'] = options.opt_arc
            self.options['opt_list']=options.opt_list
        else:
            self.options['opt_arc'] = False
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

    #플러그인 엔진에게 압축 해제 요청
    def unarc(self, file_struct):
        rname_struct=None

        try:
            if file_struct.bool_zip():
                arc_engine_id=file_struct.get_zip_engine_id()

                arc_name=file_struct.get_zip_file()
                name_in_arc=file_struct.get_zipped_file()

                for inst in self.kavmain_inst:
                    try:
                        unpack_data=inst.unarc(arc_engine_id, arc_name, name_in_arc)

                        if unpack_data:
                            rname=tempfile.mktemp(prefix='ktmp')
                            fp=open(rname, 'wb')
                            fp.write(unpack_data)
                            fp.close()

                            rname_struct=file_struct
                            rname_struct.set_target_file(rname)

                    except AttributeError:
                        continue
                return rname_struct
        except IOError:
            pass
        return None

    #플러그인 엔진에게 압축파일의 내부 리스트를 요청
    def arclist(self, file_struct, fileformat):
        arc_list=[]
        file_scan_list=[]

        rname=file_struct.get_target_file()
        deep_name=file_struct.get_zip_structure_file()
        mname=file_struct.root_file()
        level=file_struct.get_level()

        #압축 엔진 모듈의 arclist 멤버 함수 호출
        for inst in self.kavmain_inst:

            try:
                if self.options['opt_arc']:
                    arc_list=inst.arclist(rname, fileformat)

                if len(arc_list):   #압축 목록이 존재한다면 추가하고 종료
                    for alist in arc_list:
                        arc_id=alist[0] #항상 압축 엔진 ID가 들어옴
                        name=alist[1]   #압축 파일의 내부 파일 이름

                        if len (deep_name): #압축 파일 내부 표시용
                            dname='%s/%s' %(deep_name, name)
                        else:
                            dname='%s' %name

                        fs=file.FileStruct()
                        #기존 level보다 1증가시켜 압축 깊이가 깊어짐을 표시
                        fs.set_archive(arc_id, rname, name, dname, mname, False, False, level+1)
                        file_scan_list.append(fs)

                    self.result['Packed']+=1
                    break
            except AttributeError:
                continue

        return file_scan_list

    #플러그인 엔진에게 파일 포맷 분석을 요청
    def format(self, file_struct):
        ret={}
        filename=file_struct.get_target_file()

        try:
            fp=open(filename, 'rb')
            mm=mmap.mmap(fp.fileno(), 0, access=mmap.ACCESS_READ)

            #엔진 모듈의 format 멤버 함수 호출
            for inst in self.kavmain_inst:
                try:
                    ff=inst.format(mm, filename)
                    if ff:
                        ret.update(ff)
                except AttributeError:
                    pass
            mm.close()
            fp. close()
        except IOError:
            pass

        return ret

    #악성코드를 치료
    def __disinfect_process(self, ret_value, disinfect_callback_fn, action_type):
        if action_type==menu.MENU_IGNORE:   #치료 무시
            return

        t_file_info=ret_value['file_struct']    #검사 파일 정보
        mid=ret_value['virus_id']   #악성코드 ID
        eid=ret_value['engine_id']  #악성코드를 진단한 엔진 ID

        d_fname=t_file_info.get_target_file()
        d_ret=False

        if action_type==menu.MENU_DISINFECT:    #치료 옵션이 설정됐나?
            d_ret=self.disinfect(d_fname, mid, eid)
            if d_ret:
                self.result['Disinfected_files'] +=1    #치료 파일 수
        elif action_type==menu.MENU_DELETE:     #삭제 옵션이 설정 됐나?
            try:
                os.remove(d_fname)
                d_ret=True
                self.result['Deleted_files'] +=1        #삭제 파일 수
            except IOError:
                d_ret=False

        t_file_info.set_bool_modified(d_ret)   #치료(수정/삭제) 여부 표시

        if isinstance(disinfect_callback_fn, types.FunctionType):
            disinfect_callback_fn(ret_value, action_type)


    # update_info 내부의 압축을 처리
    # 입력값 : p_file_info - update_info의 마지막 파일 정보 구조체
    # 리턴값 : 갱신된 파일 정보 구조체
    def __update_arc_file_struct(self, p_file_info):
        # 실제 압축 파일 이름이 같은 파일을 모두 추출한다.
        t = []

        arc_level = p_file_info.get_level()

        while len(self.update_info):
            if self.update_info[-1].get_level() == arc_level:
                t.append(self.update_info.pop())
            else:
                break

        t.reverse()  # 순위를 바꾼다.

        # 리턴값이 될 파일 정보 (압축 파일의 최상위 파일)
        ret_file_info = self.update_info.pop()

        # 업데이트 대상 파일들이 수정 여부를 체크한다
        b_update = False

        for finfo in t:
            if finfo.bool_modified():
                b_update = True
                break

        if b_update:  # 수정된 파일이 존재한다면 재압축 진행
            arc_name = t[0].get_zip_file()
            arc_engine_id = t[0].get_zip_engine_id()

            for inst in self.kavmain_inst:
                try:
                    ret=inst.mkarc(arc_engine_id, arc_name, t)
                    if ret: #최종 압축 성공
                        break
                except AttributeError:
                    continue
            ret_file_info.set_bool_modified(True)  #수정 여부 표시

        #압축된 파일들 모두 삭제
        for tmp in t:
            t_fname=tmp.get_target_file()
            #플러그인 엔진에 의해 파일이 치료(삭제)됐을 수 있다
            if os.path.exists(t_fname):
                os.remove(t_fname)

        return ret_file_info


    # update_info를 갱신
    # 입력값 : file_struct        - 파일 정보 구조체
    #          immediately_flag   - update_info 모든 정보 갱신 여부
    def __update_process(self, file_struct, update_callback_fn, immediately_flag=False):
        # 압축 파일 정보의 재압축을 즉시하지 않고 내부 구성을 확인하여 처리한다.
        if immediately_flag is False:
            if len(self.update_info) == 0:  # 아무런 파일이 없으면 추가
                self.update_info.append(file_struct)
            else:
                n_file_info = file_struct  # 현재 작업 파일 정보
                p_file_info = self.update_info[-1]  # 직전 파일 정보

                # 마스터 파일이 같은가? (압축 엔진이 있을때만 유효)
                if p_file_info.root_file() == n_file_info.root_file():
                    if p_file_info.get_level() <= n_file_info.get_level():
                        # 마스터 파일이 같고 계속 압축 깊이가 깊어지면 계속 누적
                        self.update_info.append(n_file_info)
                    else:
                        ret_file_info = self.__update_arc_file_struct(p_file_info)
                        self.update_info.append(ret_file_info)  # 결과 파일 추가
                        self.update_info.append(n_file_info)  # 다음 파일 추가
                else:
                    #새로운 파일이 시작되므로 self.update_info 내부 모두 정리
                    immediately_flag = True

        # 압축 파일 정보를 이용해 즉시 압축하여 최종 마스터 파일로 재조립한다.
        if immediately_flag and len(self.update_info) >1:
            ret_file_info=None

            while len(self.update_info):
                p_file_info = self.update_info[-1]  # 직전 파일 정보
                ret_file_info = self.__update_arc_file_struct(p_file_info)

                if len(self.update_info):  # 최상위 파일이 아니면 하위 결과 추가
                    self.update_info.append(ret_file_info)

            if isinstance(update_callback_fn, types.FunctionType) and ret_file_info:
                update_callback_fn(ret_file_info)