from typing import List, Dict, Any, Tuple

# ===========================
# [UI 데이터 초기화 및 상태 관리]
# ===========================

def prepare_edit_data(base_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """생성된 매칭 레시피를 기반으로 UI 수동 검수 테이블에 바인딩할 데이터 상태를 초기화합니다.

    자동화 알고리즘이 100% 완벽할 수 없으므로, 사용자가 병합 결과를 눈으로 확인하고(Human-in-the-loop) 
    체크박스를 통해 페이지를 선택/해제할 수 있도록 각 레코드의 초기 체크 상태(Boolean)를 부여합니다. 
    알고리즘의 결과를 기본값으로 신뢰하되, 언제든 사용자가 오버라이드할 수 있는 유연성을 제공합니다.

    Args:
        base_data (List[Dict[str, Any]]): `generate_matching_data`에서 도출된 원본 병합 레시피.

    Returns:
        List[Dict[str, Any]]: `jul_checked`와 `yaboot_checked` 플래그가 주입된 UI 편집용 데이터 배열.
    """
    # 결과 저장을 위한 빈 리스트 생성
    edit_data: List[Dict[str, Any]] = []
    
    # 원본 데이터를 순회하며 UI 플래그 주입
    for item in base_data:
        # 원본 데이터 훼손 방지를 위해 복사본 생성
        new_item = item.copy()
        
        # 매칭된 페이지인 경우 줄필기를 기본으로 선택
        if item["type"] == "matched":
            new_item["jul_checked"] = True
            new_item["yaboot_checked"] = False
        # 줄필기만 존재하는 경우 줄필기 선택
        elif item["type"] == "jul_only":
            new_item["jul_checked"] = True
            new_item["yaboot_checked"] = False
        # 야붙만 존재하는 경우 야붙 선택
        elif item["type"] == "yaboot_only":
            new_item["jul_checked"] = False
            new_item["yaboot_checked"] = True
            
        # 처리된 항목을 리스트에 추가
        edit_data.append(new_item)
        
    return edit_data

# ===========================
# [사용자 변경 사항 확정 및 정제]
# ===========================

def save_edits(edit_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """사용자의 체크박스 수정 사항을 반영하여 최종적으로 병합에 사용될 확정 레시피를 도출합니다.

    UI 레이어에서 발생한 사용자의 상호작용 결과를 Service 레이어의 데이터 구조로 다시 정제합니다. 
    체크 해제된 항목(병합에서 제외할 페이지)을 필터링하여 실제 디스크 I/O 단계로 넘어갈 
    순도 높은 데이터만 남깁니다.

    Args:
        edit_data (List[Dict[str, Any]]): 사용자의 수동 검수를 거친 상태 데이터 배열.

    Returns:
        List[Dict[str, Any]]: 병합 대상에서 제외된 항목들이 필터링된 최종 확정 레시피.
    """
    # 확정된 항목을 담을 리스트 초기화
    new_base: List[Dict[str, Any]] = []
    
    # 체크된 상태를 확인하여 병합 대상만 필터링
    for item in edit_data:
        # 매칭 항목 중 줄필기가 선택된 경우
        if item["type"] == "matched" and item.get("jul_checked"):
            new_base.append(item)
        # 줄필기 단독 항목 중 줄필기가 선택된 경우
        elif item["type"] == "jul_only" and item.get("jul_checked"):
            new_base.append(item)
        # 야붙 단독 항목 중 야붙이 선택된 경우
        elif item["type"] == "yaboot_only" and item.get("yaboot_checked"):
            new_base.append(item)
            
    return new_base

# ===========================
# [레코드 분할 및 순서 조작]
# ===========================

def split_item_on_yaboot_check(item: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """사용자가 'matched' 상태의 페이지에서 특정 이벤트를 발생시켰을 때 하나의 항목을 두 개로 분할합니다.

    알고리즘이 '유사하다'고 판단하여 하나의 행(Row)으로 묶어둔 페이지 쌍(Pair)에 대해, 
    사용자가 "이 두 페이지는 다르니 분리해서 개별적으로 넣고 싶다"고 체크를 변경했을 때 대응하는 로직입니다. 
    하나의 레코드를 두 개의 독립적인 단일 소스 레코드(`jul_only`, `yaboot_only`)로 분할 반환합니다.

    Args:
        item (Dict[str, Any]): 분할할 원본 'matched' 상태의 레코드.

    Returns:
        Tuple[Dict[str, Any], Dict[str, Any]]: 분리되어 새로 생성된 줄필기 전용 레코드와 야붙 전용 레코드의 튜플.
    """
    # 줄필기 단독 항목으로 분할 생성
    item_jul = {
        "type": "jul_only",
        "save_name": item["save_name"],
        "jul": item["jul"], "yaboot": None,
        "jul_checked": item.get("jul_checked", False), "yaboot_checked": False,
        "metrics": "[분할됨]\n줄필기 단독"
    }
    
    # 야붙 단독 항목으로 분할 생성
    item_yaboot = {
        "type": "yaboot_only",
        "save_name": item["save_name"],
        "jul": None, "yaboot": item["yaboot"],
        "jul_checked": False, "yaboot_checked": True,
        "metrics": "[분할됨]\n야붙 단독"
    }
    
    return item_jul, item_yaboot

def swap_items(edit_data: List[Dict[str, Any]], idx: int, direction: int) -> List[Dict[str, Any]]:
    """레시피 배열 내에서 특정 항목의 위치를 위/아래로 변경합니다.

    UI의 위/아래 화살표 버튼을 클릭했을 때 호출되어, 최종 병합본에 삽입될 페이지의 순서(Order)를 
    수동으로 조작하는 유틸리티 메서드입니다. 배열 인덱스 바운더리를 안전하게 검사하여 크래시를 방지합니다.

    Args:
        edit_data (List[Dict[str, Any]]): 순서를 변경할 전체 레시피 데이터 리스트.
        idx (int): 이동시킬 대상 항목의 현재 인덱스.
        direction (int): 이동 방향 (보통 위로 이동은 -1, 아래로 이동은 1).

    Returns:
        List[Dict[str, Any]]: 순서 변경(Swap)이 반영된 새로운 데이터 리스트.
    """
    # 목표 인덱스 계산
    target_idx = idx + direction
    
    # 목표 인덱스가 배열 범위를 벗어나지 않는지 확인
    if 0 <= target_idx < len(edit_data):
        # 위치 맞교환 (Swap)
        edit_data[idx], edit_data[target_idx] = edit_data[target_idx], edit_data[idx]
        
    return edit_data

