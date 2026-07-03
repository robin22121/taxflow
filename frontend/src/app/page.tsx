import type { Metadata } from "next";
import Link from "next/link";

import { AuthRedirect } from "@/components/auth-redirect";
import { BetaSignupForm, WaitlistCounter } from "@/components/beta-signup";

export const metadata: Metadata = {
  title: "이지원천 — 원천세 업무, AI로 끝내는 세무사무소",
  description:
    "카톡으로 받은 급여 자료를 AI가 정형화해 SmartA 급여대장 엑셀까지 한 번에. 자료 수집부터 검증·신고·급여명세서 교부까지 원천세 업무를 자동화합니다.",
};

/* ============================================================
   이지원천 랜딩 페이지 (홈)
   디자인 토큰: blue-600(#1370CE) 액센트 · Pretendard · rounded-full
   · double-bezel 카드 — frontend 앱과 동일한 디자인 언어 사용
   ============================================================ */

function LogoMark({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <div className="w-8 h-8 rounded-xl bg-gray-900 text-white flex items-center justify-center text-[15px] font-extrabold">
        이
      </div>
      <span className="text-[17px] font-bold tracking-tight text-gray-900">
        이지원천
      </span>
    </div>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-600/8 text-blue-600 text-[10.5px] font-semibold uppercase tracking-widest">
      {children}
    </span>
  );
}

// 카카오 채널 친구 추가 — 앱 키 없이 동작하는 친구추가 딥링크 (채널 ID: _lxazsX)
const KAKAO_CHANNEL_ADD_URL = "http://pf.kakao.com/_lxazsX/friend";

function KakaoChannelButton({ className = "" }: { className?: string }) {
  return (
    <a
      href={KAKAO_CHANNEL_ADD_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center justify-center gap-2 rounded-full bg-[#FEE500] px-5 py-2.5 text-[13.5px] font-semibold text-[#191600] transition-all hover:brightness-95 ${className}`}
    >
      <span className="text-[15px]">💬</span>
      카카오 채널 추가
    </a>
  );
}

export default function LandingPage() {
  return (
    <div className="bg-white text-gray-900">
      {/* 로그인 사용자는 대시보드로 (마케팅 페이지는 비로그인 방문자용) */}
      <AuthRedirect />

      {/* ───────────────── Nav ───────────────── */}
      <header className="sticky top-0 z-50 border-b border-gray-200/70 bg-white/80 backdrop-blur-md">
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <LogoMark />
          <div className="hidden items-center gap-7 text-[13px] font-medium text-gray-600 md:flex">
            <a href="#features" className="transition-colors hover:text-gray-900">
              기능
            </a>
            <a href="#how" className="transition-colors hover:text-gray-900">
              작동 방식
            </a>
            <a href="#payslip" className="transition-colors hover:text-gray-900">
              급여명세서
            </a>
            <a href="#pricing" className="transition-colors hover:text-gray-900">
              요금
            </a>
            <a href="#trust" className="transition-colors hover:text-gray-900">
              보안
            </a>
            <a href="#beta" className="font-semibold text-blue-600 transition-colors hover:text-blue-700">
              베타 신청
            </a>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="hidden rounded-full px-3.5 py-2 text-[13px] font-medium text-gray-700 transition-colors hover:bg-gray-50 sm:inline-flex"
            >
              로그인
            </Link>
            <Link
              href="/register"
              className="inline-flex items-center justify-center rounded-full border border-blue-600 bg-blue-600 px-4 py-2 text-[13px] font-medium text-white shadow-[0_1px_0_rgba(255,255,255,0.2)_inset,0_8px_20px_-8px_rgba(19,112,206,0.45)] transition-all hover:brightness-110"
            >
              무료로 시작
            </Link>
          </div>
        </nav>
      </header>

      {/* ───────────────── Hero ───────────────── */}
      <section className="relative overflow-hidden">
        {/* background glow */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-[-10%] -z-10 mx-auto h-[480px] max-w-4xl rounded-full bg-blue-500/10 blur-[120px]"
        />
        <div className="mx-auto max-w-6xl px-5 pt-20 pb-16 text-center sm:pt-28">
          <div className="mb-6 flex justify-center">
            <Eyebrow>세무사무소를 위한 원천세 AI</Eyebrow>
          </div>
          <h1 className="mx-auto max-w-3xl text-[34px] font-extrabold leading-[1.18] tracking-tight text-gray-900 sm:text-[52px] sm:leading-[1.12]">
            카톡으로 받은 급여 자료,
            <br className="hidden sm:block" />{" "}
            <span className="bg-gradient-to-r from-blue-600 to-blue-500 bg-clip-text text-transparent">
              AI가 SmartA 엑셀까지
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-[15px] leading-relaxed text-gray-500 sm:text-[17px]">
            거래처가 보내는 카톡·엑셀·사진을 그대로 받아 AI가 정형화하고,
            검증부터 급여대장 엑셀 생성·급여명세서 교부까지. 매월 반복되는
            원천세 업무 시간을 최대 80%까지 줄입니다.
          </p>
          <div className="mt-7 flex justify-center">
            <span className="inline-flex items-center gap-2 rounded-full border border-blue-600/20 bg-blue-600/[0.06] px-4 py-1.5 text-[13px] font-semibold text-blue-700 sm:text-[14px]">
              🎁 지금 가입 시 <span className="font-extrabold">6개월 무료</span> + 이후{" "}
              <span className="font-extrabold">1년 50% 할인</span>
            </span>
          </div>
          <div className="mt-5 flex justify-center">
            <WaitlistCounter />
          </div>
          <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/register"
              className="inline-flex w-full items-center justify-center rounded-full border border-blue-600 bg-blue-600 px-6 py-3 text-[14px] font-semibold text-white shadow-[0_1px_0_rgba(255,255,255,0.2)_inset,0_10px_28px_-10px_rgba(19,112,206,0.55)] transition-all hover:brightness-110 sm:w-auto"
            >
              무료로 시작하기 →
            </Link>
            <a
              href="#how"
              className="inline-flex w-full items-center justify-center rounded-full border border-gray-300 bg-white px-6 py-3 text-[14px] font-semibold text-gray-900 transition-colors hover:border-gray-400 sm:w-auto"
            >
              작동 방식 보기
            </a>
          </div>
          <p className="mt-4 text-[12.5px] text-gray-400">
            신용카드 없이 시작 · 1인 사무소부터 세무법인까지
          </p>

          {/* Product mockup — double bezel, app과 동일 */}
          <div className="mx-auto mt-16 max-w-4xl">
            <div className="rounded-[22px] border border-gray-300 bg-gray-50 p-2 shadow-[0_1px_0_rgba(28,25,23,0.04),0_40px_80px_-32px_rgba(28,25,23,0.22)]">
              <div className="overflow-hidden rounded-[16px] border border-black/[0.06] bg-white shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
                <HeroMock />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ───────────────── Stat strip ───────────────── */}
      <section className="border-y border-gray-200 bg-gray-50/60">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px px-5 py-10 md:grid-cols-4">
          {[
            { v: "80%", l: "원천세 업무 시간 절감" },
            { v: "1번", l: "카톡 공유로 자료 입력 완료" },
            { v: "24열", l: "SmartA 급여대장 양식 일치" },
            { v: "0", l: "수임처 사장님 추가 작업" },
          ].map((s) => (
            <div key={s.l} className="px-2 text-center">
              <div className="t-num text-[30px] font-extrabold tracking-tight text-gray-900 sm:text-[36px]">
                {s.v}
              </div>
              <div className="mt-1 text-[12.5px] text-gray-500">{s.l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ───────────────── Problem ───────────────── */}
      <section className="mx-auto max-w-6xl px-5 py-24">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow>왜 필요한가</Eyebrow>
          <h2 className="mt-4 text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
            매월 돌아오는 원천세,
            <br />
            가장 힘든 건 &ldquo;자료 모으기&rdquo;입니다
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-gray-500">
            거래처마다 카톡·전화·엑셀·사진으로 제각각 보내는 비정형 자료를
            직원이 손으로 정리하고, 신규·퇴사·이상치를 일일이 확인하고,
            간이세액과 4대보험을 수기로 계산합니다.
          </p>
        </div>
        <div className="mt-14 grid gap-4 md:grid-cols-3">
          {[
            {
              t: "비정형 자료의 늪",
              d: "“저번 달이랑 똑같아요”, 사진 한 장, 메모 엑셀… 형식이 제각각이라 결국 사람이 다시 정리해야 합니다.",
            },
            {
              t: "끝없는 후속 질문",
              d: "신규 입사자인지 동명이인인지, 급여가 왜 늘었는지. 첫 달에는 확인 전화만 하루 종일 돌립니다.",
            },
            {
              t: "수기 계산의 휴먼 에러",
              d: "간이세액·4대보험·차인지급액을 손으로 계산하다 보면 한 건의 실수가 신고 정정으로 이어집니다.",
            },
          ].map((p) => (
            <div
              key={p.t}
              className="rounded-[14px] border border-gray-200 bg-white p-6 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]"
            >
              <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-red-50 text-red-500">
                <span className="text-[15px]">!</span>
              </div>
              <h3 className="text-[15px] font-semibold text-gray-900">{p.t}</h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-gray-500">
                {p.d}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ───────────────── Value ladder (3단 가치 사다리) ───────────────── */}
      <section className="mx-auto max-w-6xl px-5 pb-24">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow>이지원천이 주는 가치</Eyebrow>
          <h2 className="mt-4 text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
            시간을 되찾고, 실수를 없애고,
            <br />
            거래처를 늘립니다
          </h2>
          <p className="mt-4 text-[15px] leading-relaxed text-gray-500">
            단순한 시간 절약을 넘어, 사무소의 수익 구조까지 바꾸는 세 단계의 가치.
          </p>
        </div>
        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {[
            {
              step: "STEP 1",
              t: "시간을 되찾다",
              d: "거래처가 보낸 카톡·엑셀·사진을 AI가 자동 정형화. 손으로 옮기고 다시 묻던 자료 수집 시간을 매월 수십 시간 절감합니다.",
              metric: "원천세 업무 시간 80%↓",
            },
            {
              step: "STEP 2",
              t: "실수를 없애다",
              d: "신규·퇴사·전월 대비 급증을 자동 감지하고, 간이세액·4대보험을 정확히 계산. 신고 정정으로 이어지는 휴먼 에러를 차단합니다.",
              metric: "수기 계산 오류 0",
            },
            {
              step: "STEP 3",
              t: "거래처를 늘리다",
              d: "급여명세서 교부·4대보험 신고까지 묶어 수임처에 새 가치를 제안. 같은 인력으로 더 많은 거래처를 감당할 수 있습니다.",
              metric: "신규 수임 제안 무기",
            },
          ].map((v, i) => (
            <div
              key={v.t}
              className="relative rounded-[18px] border border-gray-200 bg-white p-7 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]"
            >
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-blue-600 text-[14px] font-extrabold text-white">
                  {i + 1}
                </span>
                <span className="t-num text-[11px] font-bold uppercase tracking-widest text-blue-600">
                  {v.step}
                </span>
              </div>
              <h3 className="mt-4 text-[18px] font-bold tracking-tight text-gray-900">
                {v.t}
              </h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-gray-500">
                {v.d}
              </p>
              <div className="mt-5 inline-flex items-center rounded-full bg-blue-600/8 px-3 py-1 text-[12px] font-semibold text-blue-700">
                {v.metric}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ───────────────── Features ───────────────── */}
      <section id="features" className="border-t border-gray-200 bg-gray-50/50">
        <div className="mx-auto max-w-6xl px-5 py-24">
          <div className="mx-auto max-w-2xl text-center">
            <Eyebrow>핵심 기능</Eyebrow>
            <h2 className="mt-4 text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
              수집부터 산출까지, 한 흐름으로
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-gray-500">
              경쟁 솔루션이 손대지 못한 &lsquo;자료 수집&rsquo; 단계부터
              자동화합니다.
            </p>
          </div>
          <div className="mt-14 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[
              {
                tag: "AI 파싱",
                t: "기존 소통 방식 그대로",
                d: "거래처는 늘 쓰던 카톡·엑셀·사진으로 보내면 끝. AI가 비정형 자료를 자동으로 급여 항목으로 정형화합니다.",
              },
              {
                tag: "스마트 매칭",
                t: "직원 매칭 · 이상치 감지",
                d: "전월 데이터 기준으로 기존 직원을 자동 매칭하고, 신규·퇴사 의심자와 전월 대비 급증(+42%)을 자동으로 하이라이트합니다.",
              },
              {
                tag: "엑셀 생성",
                t: "SmartA 급여대장 원클릭",
                d: "더존 SmartA 24컬럼 공식 양식과 일치하는 엑셀을 자동 생성. 다운로드해서 그대로 업로드하면 됩니다.",
              },
              {
                tag: "급여명세서",
                t: "교부 의무까지 자동 해결",
                d: "근로기준법 제48조 양식 급여명세서를 자동 생성해 직원에게 발송. 수임처 사장님이 할 일은 없습니다.",
              },
              {
                tag: "4대보험",
                t: "자격취득·상실 신고서",
                d: "동일한 직원·급여 데이터를 재활용해 자격취득/상실·보수월액 변경 신고서 엑셀까지 자동으로 만듭니다.",
              },
              {
                tag: "검증",
                t: "세무사 최종 승인",
                d: "SmartA와 동일한 화면으로 검토하고, ‘확인필요만 보기’로 이상치만 모아 봅니다. 모든 신고는 세무사가 승인합니다.",
              },
            ].map((f) => (
              <div
                key={f.t}
                className="group rounded-[14px] border border-gray-200 bg-white p-6 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)] transition-all hover:border-blue-300 hover:shadow-[0_1px_0_rgba(28,25,23,0.04),0_14px_32px_-18px_rgba(19,112,206,0.25)]"
              >
                <span className="inline-flex items-center rounded-full bg-blue-600/8 px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider text-blue-600">
                  {f.tag}
                </span>
                <h3 className="mt-3 text-[16px] font-semibold tracking-tight text-gray-900">
                  {f.t}
                </h3>
                <p className="mt-2 text-[13.5px] leading-relaxed text-gray-500">
                  {f.d}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ───────────────── How it works ───────────────── */}
      <section id="how" className="mx-auto max-w-6xl px-5 py-24">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow>작동 방식</Eyebrow>
          <h2 className="mt-4 text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
            네 단계면 신고 준비 끝
          </h2>
        </div>
        <div className="mt-16 grid gap-10 md:grid-cols-4 md:gap-6">
          {[
            {
              n: "01",
              t: "요청",
              d: "대시보드에서 버튼 한 번. 등록된 거래처에 자료 요청 알림톡이 일괄 발송됩니다.",
            },
            {
              n: "02",
              t: "수집",
              d: "거래처는 늘 쓰던 방식대로 전송. 카톡에서 ‘공유하기’ 한 번이면 입력 완료, AI가 즉시 파싱합니다.",
            },
            {
              n: "03",
              t: "검증",
              d: "급여대장과 동일한 화면에서 이상치만 모아 보고 검토·승인합니다.",
            },
            {
              n: "04",
              t: "생성 · 신고",
              d: "SmartA 급여대장 엑셀을 받아 업로드하고, 급여명세서는 직원에게 자동 교부됩니다.",
            },
          ].map((s) => (
            <div key={s.n} className="relative">
              <div className="t-num text-[13px] font-bold tracking-widest text-blue-600">
                {s.n}
              </div>
              <h3 className="mt-2 text-[17px] font-semibold tracking-tight text-gray-900">
                {s.t}
              </h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-gray-500">
                {s.d}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ───────────────── Demo video (시연 영상 슬롯) ───────────────── */}
      <section id="demo" className="border-t border-gray-200 bg-gray-50/50">
        <div className="mx-auto max-w-4xl px-5 py-24">
          <div className="mx-auto max-w-2xl text-center">
            <Eyebrow>제품 시연</Eyebrow>
            <h2 className="mt-4 text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
              카톡 한 장이 엑셀이 되는 과정,
              <br />
              영상으로 확인하세요
            </h2>
          </div>
          {/* Supademo 인터랙티브 데모 */}
          <div className="mx-auto mt-12 w-full overflow-hidden rounded-[20px] border border-gray-300 bg-gray-900 shadow-[0_30px_60px_-30px_rgba(28,25,23,0.4)]">
            <div className="relative w-full aspect-[1.26]">
              <iframe
                src="https://app.supademo.com/embed/cmqiv9gtv0awiqmx1ockfizeq?embed_v=2&utm_source=embed"
                loading="lazy"
                title="Process Employee Requests and Approve Salary Items in Easy One Chon"
                allow="clipboard-write"
                allowFullScreen
                className="absolute left-0 top-0 h-full w-full border-0"
              />
            </div>
          </div>
        </div>
      </section>

      {/* ───────────────── Payslip highlight ───────────────── */}
      <section id="payslip" className="border-y border-gray-200 bg-gray-900 text-white">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-24 md:grid-cols-2">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-widest text-blue-300">
              세무사의 영업 무기
            </span>
            <h2 className="mt-4 text-[28px] font-bold leading-snug tracking-tight sm:text-[34px]">
              &ldquo;맡기면 급여명세서 교부 의무도
              <br />
              자동으로 해결됩니다&rdquo;
            </h2>
            <p className="mt-5 text-[15px] leading-relaxed text-gray-300">
              급여명세서 교부는 법적 의무지만 미교부 사업장이 여전히 많습니다.
              이지원천은 신고 데이터로 급여명세서를 자동 생성해 직원에게 바로
              발송합니다. 수임처 사장님의 추가 작업은 없고, 세무사에게는 새로운
              수임 제안이 됩니다.
            </p>
            <ul className="mt-7 space-y-3 text-[14px] text-gray-200">
              {[
                "근로기준법 제48조 양식 자동 생성",
                "직원에게 카톡·문자로 자동 발송",
                "과태료 리스크(최대 100만 원/인·월) 사전 차단",
              ].map((li) => (
                <li key={li} className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-blue-500/20 text-[11px] text-blue-300">
                    ✓
                  </span>
                  {li}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-[20px] border border-white/10 bg-white/[0.04] p-2">
            <PayslipMock />
          </div>
        </div>
      </section>

      {/* ───────────────── Pricing (2단) + 18개월 락인 표 ───────────────── */}
      <section id="pricing" className="mx-auto max-w-6xl px-5 py-24">
        <div className="mx-auto max-w-2xl text-center">
          <Eyebrow>요금제</Eyebrow>
          <h2 className="mt-4 text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
            거래처 수에 따라, 단 두 가지
          </h2>
          <p className="mt-4 text-[15px] text-gray-500">
            복잡한 단계 없이 사무소 규모에 맞는 정액 요금. 직원 한 명의 하루치 인건비로
            매월 반복되는 원천세 업무를 덜어내세요.
          </p>
        </div>

        {/* 정가 2단 */}
        <div className="mx-auto mt-14 grid max-w-3xl gap-5 md:grid-cols-2">
          {[
            {
              name: "기본",
              price: "20만",
              sub: "수임 거래처 100곳 미만",
              feats: [
                "AI 자료 수집 · 정형화",
                "직원 매칭 · 이상치 감지",
                "SmartA 급여대장 엑셀 생성",
                "급여명세서 자동 교부",
                "4대보험 신고서 엑셀",
              ],
              highlight: false,
            },
            {
              name: "대형",
              price: "25만",
              sub: "수임 거래처 100곳 이상",
              feats: [
                "기본의 모든 기능",
                "거래처 수 제한 없음",
                "세무법인 부서 단위 운영",
                "홈택스 신고 보조",
                "우선 지원 · 전담 온보딩",
              ],
              highlight: true,
            },
          ].map((p) => (
            <div
              key={p.name}
              className={
                p.highlight
                  ? "relative rounded-[18px] border-2 border-blue-600 bg-white p-7 shadow-[0_1px_0_rgba(28,25,23,0.04),0_24px_48px_-24px_rgba(19,112,206,0.35)]"
                  : "rounded-[18px] border border-gray-200 bg-white p-7 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]"
              }
            >
              {p.highlight && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-blue-600 px-3 py-1 text-[11px] font-semibold text-white shadow-[0_8px_20px_-8px_rgba(19,112,206,0.6)]">
                  거래처 100곳 이상
                </span>
              )}
              <h3 className="text-[15px] font-semibold text-gray-900">{p.name}</h3>
              <p className="mt-1 text-[12.5px] text-gray-500">{p.sub}</p>
              <div className="mt-5 flex items-baseline gap-1">
                <span className="t-num text-[36px] font-extrabold tracking-tight text-gray-900">
                  {p.price}
                </span>
                <span className="text-[14px] text-gray-500">원 / 월</span>
              </div>
              <ul className="mt-6 space-y-3">
                {p.feats.map((f) => (
                  <li
                    key={f}
                    className="flex items-start gap-2.5 text-[13.5px] text-gray-700"
                  >
                    <span className="mt-0.5 flex h-4 w-4 flex-none items-center justify-center rounded-full bg-blue-600/10 text-[10px] text-blue-600">
                      ✓
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
              <a
                href="#beta"
                className={
                  p.highlight
                    ? "mt-7 inline-flex w-full items-center justify-center rounded-full border border-blue-600 bg-blue-600 px-4 py-2.5 text-[13px] font-semibold text-white shadow-[0_1px_0_rgba(255,255,255,0.2)_inset,0_8px_20px_-8px_rgba(19,112,206,0.45)] transition-all hover:brightness-110"
                    : "mt-7 inline-flex w-full items-center justify-center rounded-full border border-gray-300 bg-white px-4 py-2.5 text-[13px] font-semibold text-gray-900 transition-colors hover:border-gray-400"
                }
              >
                베타 신청하고 혜택 받기
              </a>
            </div>
          ))}
        </div>

        {/* 18개월 락인 표 — 베타/얼리버드 가입 혜택 */}
        <div className="mx-auto mt-16 max-w-4xl">
          <div className="mb-6 text-center">
            <Eyebrow>지금 가입하면</Eyebrow>
            <h3 className="mt-3 text-[22px] font-bold tracking-tight text-gray-900 sm:text-[26px]">
              먼저 합류할수록 더 오래 무료, 더 오래 반값
            </h3>
            <p className="mt-2 text-[13.5px] text-gray-500">
              가입 시점의 혜택이 그대로 고정됩니다. 베타는 최대 18개월간 혜택이 유지됩니다.
            </p>
          </div>
          <div className="overflow-hidden rounded-[18px] border border-gray-200 bg-white shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]">
            <div className="grid grid-cols-[1.1fr_1fr_1fr_1.1fr] bg-gray-50 px-5 py-3 text-[12px] font-semibold uppercase tracking-wider text-gray-500">
              <span>구분</span>
              <span className="text-center">가입 기한</span>
              <span className="text-center">무료 기간</span>
              <span className="text-center">이후 할인</span>
            </div>
            {[
              {
                name: "베타",
                badge: "최대 18개월 혜택",
                deadline: "2026년 8월까지",
                free: "6개월 무료",
                discount: "이후 12개월 50% 할인",
                highlight: true,
              },
              {
                name: "얼리버드",
                badge: "12개월 혜택",
                deadline: "2026년 12월까지",
                free: "6개월 무료",
                discount: "이후 6개월 50% 할인",
                highlight: false,
              },
              {
                name: "정가",
                badge: null,
                deadline: "상시",
                free: "—",
                discount: "기본 20만 / 100곳 이상 25만",
                highlight: false,
              },
            ].map((row) => (
              <div
                key={row.name}
                className={
                  (row.highlight ? "bg-blue-600/[0.03] " : "") +
                  "grid grid-cols-[1.1fr_1fr_1fr_1.1fr] items-center border-t border-gray-100 px-5 py-4 text-[13.5px]"
                }
              >
                <span className="flex flex-col gap-1">
                  <span className="font-bold text-gray-900">{row.name}</span>
                  {row.badge && (
                    <span className="inline-flex w-fit rounded-full bg-blue-600/10 px-2 py-0.5 text-[10.5px] font-semibold text-blue-700">
                      {row.badge}
                    </span>
                  )}
                </span>
                <span className="text-center text-gray-600">{row.deadline}</span>
                <span className="text-center font-semibold text-gray-900">{row.free}</span>
                <span className="text-center text-gray-600">{row.discount}</span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-center text-[12px] text-gray-400">
            표시 금액은 부가세 별도입니다. 무료·할인 혜택은 가입 시점 기준으로 자동 적용됩니다.
          </p>
        </div>
      </section>

      {/* ───────────────── Beta signup (베타 신청 + 카운터) ───────────────── */}
      <section id="beta" className="border-t border-gray-200 bg-gray-50/50">
        <div className="mx-auto grid max-w-6xl items-start gap-12 px-5 py-24 md:grid-cols-2">
          <div className="md:sticky md:top-24">
            <Eyebrow>베타 신청</Eyebrow>
            <h2 className="mt-4 text-[28px] font-bold leading-snug tracking-tight text-gray-900 sm:text-[34px]">
              지금 합류하고
              <br />
              최대 18개월 혜택을 받으세요
            </h2>
            <p className="mt-5 text-[15px] leading-relaxed text-gray-500">
              사무소 정보를 남겨 주시면 오픈 일정과 온보딩을 가장 먼저 안내드립니다.
              현재 사용 중인 세무 SW에 맞춰 마이그레이션을 도와드립니다.
            </p>
            <div className="mt-7">
              <WaitlistCounter />
            </div>
            <ul className="mt-7 space-y-3 text-[14px] text-gray-700">
              {[
                "8월까지 가입 시 6개월 무료 + 이후 12개월 50% 할인",
                "12월까지 가입 시 6개월 무료 + 이후 6개월 50% 할인",
                "가입 시점 혜택 그대로 고정",
              ].map((li) => (
                <li key={li} className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-blue-600/10 text-[11px] text-blue-600">
                    ✓
                  </span>
                  {li}
                </li>
              ))}
            </ul>
            <div className="mt-7 flex items-center gap-3">
              <KakaoChannelButton />
              <span className="text-[12.5px] text-gray-400">
                카톡으로 문의하거나 소식을 받아보세요
              </span>
            </div>
          </div>
          <BetaSignupForm />
        </div>
      </section>

      {/* ───────────────── Trust / Security ───────────────── */}
      <section id="trust" className="border-t border-gray-200 bg-gray-50/50">
        <div className="mx-auto max-w-6xl px-5 py-24">
          <div className="mx-auto max-w-2xl text-center">
            <Eyebrow>믿고 맡길 수 있는 이유</Eyebrow>
            <h2 className="mt-4 text-[28px] font-bold tracking-tight text-gray-900 sm:text-[34px]">
              세무 도메인 전문가가 만들고,
              <br />
              국내 데이터로 안전하게
            </h2>
          </div>
          <div className="mt-14 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {[
              {
                t: "국내 리전 운영",
                d: "네이버 클라우드 국내 리전에서 운영해 데이터가 국외로 나가지 않습니다.",
              },
              {
                t: "주민번호 분리 암호화",
                d: "주민번호는 AES-256으로 분리 암호화하고, AI에는 마스킹 후 전송합니다.",
              },
              {
                t: "세무 도메인 전문성",
                d: "국세청 15년 경력 전문가와 현직 세무사가 함께 설계한 업무 흐름.",
              },
              {
                t: "세무사 최종 승인",
                d: "AI는 보조할 뿐, 모든 신고는 세무사의 검토와 승인을 거칩니다.",
              },
            ].map((c) => (
              <div
                key={c.t}
                className="rounded-[14px] border border-gray-200 bg-white p-6 shadow-[0_1px_0_rgba(28,25,23,0.04),0_8px_24px_-16px_rgba(28,25,23,0.08)]"
              >
                <h3 className="text-[14.5px] font-semibold text-gray-900">
                  {c.t}
                </h3>
                <p className="mt-2 text-[13px] leading-relaxed text-gray-500">
                  {c.d}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ───────────────── Final CTA ───────────────── */}
      <section className="mx-auto max-w-6xl px-5 py-24">
        <div className="relative overflow-hidden rounded-[28px] border border-blue-600/20 bg-gradient-to-br from-blue-600 to-blue-500 px-8 py-16 text-center text-white shadow-[0_30px_60px_-30px_rgba(19,112,206,0.6)]">
          <div
            aria-hidden
            className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/10 blur-3xl"
          />
          <h2 className="text-[28px] font-bold tracking-tight sm:text-[36px]">
            이번 달 원천세부터 시작하세요
          </h2>
          <p className="mx-auto mt-4 max-w-md text-[15px] text-blue-50/90">
            카톡으로 받은 자료가 SmartA 엑셀이 되기까지. 지금 무료로
            확인해 보세요.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/register"
              className="inline-flex w-full items-center justify-center rounded-full bg-white px-6 py-3 text-[14px] font-semibold text-blue-700 shadow-[0_10px_28px_-10px_rgba(0,0,0,0.3)] transition-transform hover:-translate-y-0.5 sm:w-auto"
            >
              무료로 시작하기 →
            </Link>
            <Link
              href="/login"
              className="inline-flex w-full items-center justify-center rounded-full border border-white/30 bg-white/0 px-6 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-white/10 sm:w-auto"
            >
              로그인
            </Link>
          </div>
        </div>
      </section>

      {/* ───────────────── Footer ───────────────── */}
      <footer className="border-t border-gray-200">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 py-10 sm:flex-row">
          <LogoMark />
          <p className="text-[12.5px] text-gray-400">
            세무 업무 AI 자동화 플랫폼 · 원천세 · 4대보험 · 급여명세서
          </p>
          <div className="flex items-center gap-5 text-[12.5px] text-gray-500">
            <a href="#features" className="hover:text-gray-900">
              기능
            </a>
            <a href="#pricing" className="hover:text-gray-900">
              요금
            </a>
            <a href="#beta" className="hover:text-gray-900">
              베타 신청
            </a>
            <Link href="/blog" className="hover:text-gray-900">
              블로그
            </Link>
            <Link href="/login" className="hover:text-gray-900">
              로그인
            </Link>
            <KakaoChannelButton className="!px-3 !py-1.5 !text-[12px]" />
          </div>
        </div>
      </footer>
    </div>
  );
}

/* ============================================================
   목업 — 실제 대시보드 톤을 본뜬 정적 데모
   ============================================================ */

function HeroMock() {
  return (
    <div className="bg-gray-50">
      {/* window bar */}
      <div className="flex items-center gap-1.5 border-b border-gray-200 bg-white px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-gray-200" />
        <span className="h-2.5 w-2.5 rounded-full bg-gray-200" />
        <span className="h-2.5 w-2.5 rounded-full bg-gray-200" />
        <span className="ml-3 text-[11px] font-medium text-gray-400">
          이지원천 · 2026-06 원천세
        </span>
      </div>
      <div className="grid grid-cols-[150px_1fr] text-left">
        {/* sidebar */}
        <div className="hidden border-r border-gray-200 bg-white p-3 sm:block">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-gray-900 text-[10px] font-extrabold text-white">
              이
            </div>
            <span className="text-[12px] font-bold text-gray-900">이지원천</span>
          </div>
          {[
            ["월별 신고", true],
            ["거래처", false],
            ["4대보험", false],
            ["설정", false],
          ].map(([label, active]) => (
            <div
              key={label as string}
              className={
                active
                  ? "mb-1 rounded-lg bg-blue-600/8 px-2.5 py-1.5 text-[11.5px] font-medium text-blue-600"
                  : "mb-1 rounded-lg px-2.5 py-1.5 text-[11.5px] text-gray-500"
              }
            >
              {label as string}
            </div>
          ))}
        </div>
        {/* main */}
        <div className="p-4">
          <div className="mb-3 grid grid-cols-4 gap-2">
            {[
              ["총 거래처", "48", "곳"],
              ["수집률", "92", "%"],
              ["전체 항목", "316", "건"],
              ["상태", "검증중", ""],
            ].map(([l, v, u]) => (
              <div
                key={l}
                className="rounded-[10px] border border-gray-200 bg-white px-3 py-2"
              >
                <div className="text-[9.5px] font-medium uppercase tracking-wider text-gray-400">
                  {l}
                </div>
                <div className="mt-0.5 flex items-baseline gap-0.5">
                  <span className="t-num text-[15px] font-bold text-gray-900">
                    {v}
                  </span>
                  <span className="text-[10px] text-gray-400">{u}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="overflow-hidden rounded-[10px] border border-gray-200 bg-white">
            <div className="grid grid-cols-[1.4fr_1fr_1fr_0.8fr] border-b border-gray-200 px-3 py-2 text-[9.5px] font-medium uppercase tracking-wider text-gray-400">
              <span>직원</span>
              <span className="text-right">지급액</span>
              <span className="text-right">공제계</span>
              <span className="text-right">상태</span>
            </div>
            {[
              ["김서연", "3,200,000", "281,400", "확인", "ok"],
              ["이준호", "2,850,000", "246,900", "확인", "ok"],
              ["박민지 (신규?)", "4,050,000", "—", "확인필요", "warn"],
              ["정우성", "3,100,000", "271,300", "확인", "ok"],
            ].map(([name, pay, ded, st, tone]) => (
              <div
                key={name}
                className="grid grid-cols-[1.4fr_1fr_1fr_0.8fr] items-center border-b border-gray-100 px-3 py-2 text-[11px] last:border-0"
              >
                <span className="font-medium text-gray-800">{name}</span>
                <span className="t-num text-right text-gray-600">{pay}</span>
                <span className="t-num text-right text-gray-600">{ded}</span>
                <span className="text-right">
                  <span
                    className={
                      tone === "warn"
                        ? "inline-flex rounded-full border border-red-600/20 bg-red-50 px-1.5 py-0.5 text-[9.5px] font-medium text-red-600"
                        : "inline-flex rounded-full border border-gray-300 bg-gray-50 px-1.5 py-0.5 text-[9.5px] font-medium text-gray-600"
                    }
                  >
                    {st}
                  </span>
                </span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-[10.5px] text-gray-400">
              전월 대비 1건 급증 자동 감지됨
            </span>
            <span className="inline-flex items-center rounded-full border border-blue-600 bg-blue-600 px-3 py-1.5 text-[10.5px] font-medium text-white">
              SmartA 엑셀 생성
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function PayslipMock() {
  return (
    <div className="rounded-[14px] bg-white p-5 text-gray-900">
      <div className="flex items-center justify-between border-b border-gray-200 pb-3">
        <div>
          <div className="text-[13px] font-bold text-gray-900">급여명세서</div>
          <div className="text-[10.5px] text-gray-400">2026년 5월 · 김서연</div>
        </div>
        <span className="inline-flex items-center rounded-full bg-blue-600/10 px-2 py-0.5 text-[10px] font-medium text-blue-600">
          자동 발송됨
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2.5 text-[11.5px]">
        {[
          ["기본급", "3,000,000"],
          ["식대(비과세)", "200,000"],
          ["연장근로수당", "180,000"],
          ["소득세", "-84,850"],
          ["국민연금", "-135,000"],
          ["건강보험", "-106,350"],
        ].map(([k, v]) => (
          <div key={k} className="flex items-center justify-between">
            <span className="text-gray-500">{k}</span>
            <span className="t-num font-medium text-gray-800">{v}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2.5">
        <span className="text-[12px] font-semibold text-gray-700">
          차인지급액
        </span>
        <span className="t-num text-[15px] font-extrabold text-gray-900">
          3,053,800
        </span>
      </div>
    </div>
  );
}
